"""Boundary and verdict tests; no model download needed."""
import io
import os
import unittest
from unittest.mock import patch

os.environ["DEEPGUARD_ENABLE_MODEL"] = "0"
from fastapi.testclient import TestClient
from PIL import Image
import app


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


if __name__ == "__main__":
    unittest.main()
