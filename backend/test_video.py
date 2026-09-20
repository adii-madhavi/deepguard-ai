"""Real container decoding, bounded inputs, partial inference, and cleanup."""
import os
os.environ["DEEPGUARD_ENABLE_MODEL"] = "0"
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import av
import numpy as np
from fastapi.testclient import TestClient
import app
import video


def make_clip(duration=2, fps=12, fmt="mp4", codec="libx264"):
    buffer = io.BytesIO()
    with av.open(buffer, "w", format=fmt) as container:
        stream = container.add_stream(codec, rate=fps)
        stream.width, stream.height = 160, 96
        stream.pix_fmt = "yuv420p"
        for index in range(duration * fps):
            pixels = np.zeros((96, 160, 3), dtype=np.uint8)
            pixels[:, :, 1] = 90
            pixels[25:65, (index * 5) % 120: (index * 5) % 120 + 30] = [180, 130, 50]
            frame = av.VideoFrame.from_ndarray(pixels, format="rgb24")
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    return buffer.getvalue()


class VideoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.clip = make_clip()

    def setUp(self):
        self.client = TestClient(app.app)
        self.directories = []
        original = tempfile.TemporaryDirectory
        def temporary(*args, **kwargs):
            directory = original(*args, **kwargs)
            self.directories.append(Path(directory.name))
            return directory
        self.cleanup_patch = patch.object(app.tempfile, "TemporaryDirectory", side_effect=temporary)
        self.cleanup_patch.start()

    def tearDown(self):
        self.cleanup_patch.stop()
        self.assertTrue(all(not directory.exists() for directory in self.directories))
        self.assertFalse(app.analysis_lock.locked())

    def test_real_decode_timestamps_and_peak_score(self):
        with patch.object(app, "predict", side_effect=[0.9] + [0.1] * 11):
            response = self.client.post("/analyze/video", content=self.clip)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["summary"]["sampled_frames"], 12)
        self.assertEqual(result["summary"]["flagged_frames"], 1)
        self.assertEqual(result["verdict"], "review_recommended")
        self.assertEqual(result["ai_score"], 0.9)
        self.assertEqual(result["metadata"]["width"], 160)
        self.assertFalse(result["metadata"]["has_audio"])
        timestamps = [frame["timestamp"] for frame in result["frames"]]
        self.assertEqual(timestamps, sorted(set(timestamps)))
        self.assertGreater(timestamps[-1], 1.5)
        self.assertNotIn("file", result["frames"][0])

    def test_webm_decode_without_model(self):
        with patch.object(app, "predict", return_value=None):
            response = self.client.post("/analyze/video", content=make_clip(fmt="webm", codec="libvpx-vp9"))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["summary"]["scored_frames"], 0)
        self.assertIsNone(response.json()["ai_score"])
        self.assertEqual(response.json()["verdict"], "inconclusive")

    def test_partial_inference_does_not_mean_authentic(self):
        with patch.object(app, "predict", side_effect=[RuntimeError("failed")] + [0.1] * 11):
            result = self.client.post("/analyze/video", content=self.clip).json()
        self.assertEqual(result["model"]["status"], "partial")
        self.assertEqual(result["verdict"], "inconclusive")
        self.assertEqual(result["summary"]["scored_frames"], 11)

    def test_invalid_empty_and_oversized_uploads(self):
        for content in [b"", b"not video", b"#EXTM3U\nhttps://example.com/video"]:
            self.assertEqual(self.client.post("/analyze/video", content=content).status_code, 422)
        with patch.object(app, "MAX_VIDEO_BYTES", 8):
            self.assertEqual(self.client.post("/analyze/video", content=self.clip).status_code, 413)

    def test_decoder_timeout_cleans_up(self):
        with patch.object(video.subprocess, "run", side_effect=subprocess.TimeoutExpired("decoder", 45)):
            self.assertEqual(self.client.post("/analyze/video", content=self.clip).status_code, 422)

    def test_duration_limit(self):
        response = self.client.post("/analyze/video", content=make_clip(duration=121, fps=1))
        self.assertEqual(response.status_code, 422)
        self.assertIn("120 seconds", response.json()["detail"])

    def test_resolution_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.mp4"
            path.write_bytes(self.clip)
            with patch.object(video, "MAX_PIXELS", 10):
                with self.assertRaisesRegex(ValueError, "4K"):
                    video.decode_video(path)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--fixture":
        Path(sys.argv[2]).write_bytes(make_clip())
    else:
        unittest.main()
