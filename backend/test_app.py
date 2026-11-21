"""Boundary and verdict tests; no model download needed."""
import io
import os
import unittest
from unittest.mock import patch

os.environ["DEEPGUARD_ENABLE_MODEL"] = "0"
import asyncio
import tempfile
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image
import app
import history
import limits


def image_bytes(fmt="PNG"):
    output = io.BytesIO()
    Image.new("RGB", (32, 24), "green").save(output, format=fmt)
    return output.getvalue()


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app.app)

    def test_metadata_and_no_fabricated_score(self):
        with patch.object(app, "predict", return_value=None):
            response = self.client.post("/analyze", content=image_bytes())
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["metadata"]["width"], 32)
        self.assertEqual(result["metadata"]["height"], 24)
        self.assertEqual(result["verdict"], "inconclusive")
        self.assertIsNone(result["ai_score"])
        self.assertEqual(len(result["sha256"]), 64)

    def test_model_thresholds(self):
        for score, expected in [(0.92, "likely_ai_generated"), (0.1, "likely_natural"), (0.5, "inconclusive")]:
            with self.subTest(score=score), patch.object(app, "predict", return_value=score):
                result = self.client.post("/analyze", content=image_bytes()).json()
                self.assertEqual(result["verdict"], expected)
                self.assertEqual(result["ai_score"], score)

    def test_invalid_empty_and_unsupported_files(self):
        for body, status in [(b"not an image", 422), (b"", 422), (image_bytes("GIF"), 415)]:
            self.assertEqual(self.client.post("/analyze", content=body).status_code, status)

    def test_size_limits_and_recovery(self):
        with patch.object(app, "MAX_BYTES", 8):
            self.assertEqual(self.client.post("/analyze", content=image_bytes()).status_code, 413)
        with patch.object(Image, "MAX_IMAGE_PIXELS", 10):
            self.assertEqual(self.client.post("/analyze", content=image_bytes()).status_code, 413)
        self.assertFalse(app.analysis_lock.locked())

    def test_busy_service(self):
        app.analysis_lock.acquire()
        try:
            self.assertEqual(self.client.post("/analyze", content=image_bytes()).status_code, 429)
        finally:
            app.analysis_lock.release()

    def test_inference_failure_is_inconclusive(self):
        with patch.object(app, "predict", side_effect=RuntimeError("test failure")), self.assertLogs("deepguard", level="ERROR"):
            response = self.client.post("/analyze", content=image_bytes())
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["ai_score"])



class HardeningTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app.app)
        self.directory = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(history, "DB_PATH", os.path.join(self.directory.name, "reports.db"))
        self.db_patch.start()

    def tearDown(self):
        self.db_patch.stop()
        self.directory.cleanup()

    def test_history_is_scoped_to_client_token(self):
        alice, bob = {"X-DeepGuard-Client": "a" * 32}, {"X-DeepGuard-Client": "b" * 32}
        report = self.client.post("/analyze", content=image_bytes(),
                                  headers={**alice, "X-Filename": "my%20photo.png"}).json()
        self.client.post("/analyze", content=image_bytes())  # no token: not saved
        listed = self.client.get("/reports", headers=alice).json()
        self.assertEqual([(r["id"], r["filename"], r["media_type"]) for r in listed], [(report["id"], "my photo.png", "image")])
        self.assertEqual(self.client.get(f"/reports/{report['id']}", headers=alice).json(), report)
        self.assertEqual(self.client.get("/reports", headers=bob).json(), [])
        self.assertEqual(self.client.get(f"/reports/{report['id']}", headers=bob).status_code, 404)
        self.assertEqual(self.client.delete(f"/reports/{report['id']}", headers=bob).status_code, 404)
        self.assertEqual(self.client.delete(f"/reports/{report['id']}", headers=alice).status_code, 204)
        self.assertEqual(self.client.get("/reports", headers=alice).json(), [])
        self.assertEqual(self.client.get("/reports", headers={"X-DeepGuard-Client": "short"}).json(), [])

    def test_history_keeps_most_recent(self):
        headers = {"X-DeepGuard-Client": "c" * 32}
        with patch.object(history, "MAX_PER_OWNER", 2):
            ids = [self.client.post("/analyze", content=image_bytes(), headers=headers).json()["id"] for _ in range(3)]
        self.assertEqual({r["id"] for r in self.client.get("/reports", headers=headers).json()}, set(ids[1:]))

    def test_api_key(self):
        with patch.object(limits, "API_KEYS", ["secret-key"]):
            self.assertEqual(self.client.post("/analyze", content=image_bytes()).status_code, 401)
            self.assertEqual(self.client.get("/reports").status_code, 401)
            self.assertEqual(self.client.post("/analyze", content=image_bytes(), headers={"X-API-Key": "wrong"}).status_code, 401)
            self.assertEqual(self.client.post("/analyze", content=image_bytes(), headers={"Authorization": "Bearer secret-key"}).status_code, 200)
            self.assertEqual(self.client.get("/health").status_code, 200)

    def test_rate_limit(self):
        with patch.object(limits, "RATE_LIMIT", 2), patch.dict(limits._hits, clear=True):
            codes = [self.client.post("/analyze", content=image_bytes()).status_code for _ in range(3)]
            self.assertEqual(codes, [200, 200, 429])
            self.assertEqual(self.client.get("/reports").status_code, 200)

    def test_queue_waits_then_runs_or_times_out(self):
        async def scenario():
            limits.analysis_lock.acquire()
            asyncio.get_running_loop().call_later(0.3, limits.analysis_lock.release)
            async with limits.analysis_slot():
                self.assertTrue(limits.analysis_lock.locked())
            limits.analysis_lock.acquire()
            try:
                with patch.object(limits, "QUEUE_TIMEOUT", 0.3):
                    with self.assertRaises(HTTPException) as busy:
                        async with limits.analysis_slot():
                            pass
            finally:
                limits.analysis_lock.release()
            return busy.exception.status_code
        with patch.object(limits, "QUEUE_SIZE", 1):
            self.assertEqual(asyncio.run(scenario()), 503)
        self.assertFalse(limits.analysis_lock.locked())
        self.assertEqual(limits._waiting, 0)


if __name__ == "__main__":
    unittest.main()
