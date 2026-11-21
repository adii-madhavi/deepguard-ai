"""Audio container, segment, inference-failure and temporary-file checks."""
import os
os.environ["DEEPGUARD_ENABLE_MODEL"] = "0"
os.environ["DEEPGUARD_ENABLE_AUDIO_MODEL"] = "0"
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

import av
import numpy as np
from fastapi.testclient import TestClient
import app
import audio_analysis as audio
import audio_routes


def make_audio(seconds=7.5, rate=16000, channels=1, silent=False, noise=False):
    count = int(rate * seconds)
    samples = (np.zeros(count) if silent else 0.1 * np.random.default_rng(0).standard_normal(count).clip(-3, 3) if noise
               else 0.1 * np.sin(np.arange(count) * 2 * np.pi * 220 / rate))
    pcm = (np.repeat(samples[:, None], channels, axis=1) * 32767).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(pcm.tobytes())
    return buffer.getvalue()


def compressed_audio(fmt, codec):
    buffer = io.BytesIO()
    with av.open(buffer, "w", format=fmt) as output:
        target = output.add_stream(codec, rate=16000)
        target.layout = "mono"
        with av.open(io.BytesIO(make_audio(seconds=2))) as source:
            for frame in source.decode(audio=0):
                for packet in target.encode(frame):
                    output.mux(packet)
        for packet in target.encode():
            output.mux(packet)
    return buffer.getvalue()


class AudioTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app.app)
        self.directories = []
        original = tempfile.TemporaryDirectory
        def temporary(*args, **kwargs):
            directory = original(*args, **kwargs)
            self.directories.append(Path(directory.name))
            return directory
        self.cleanup_patch = patch.object(audio_routes.tempfile, "TemporaryDirectory", side_effect=temporary)
        self.cleanup_patch.start()

    def tearDown(self):
        self.cleanup_patch.stop()
        self.assertTrue(all(not directory.exists() for directory in self.directories))
        self.assertFalse(app.analysis_lock.locked())

    def test_resampling_segments_and_peak(self):
        with patch.object(audio, "predict", side_effect=[0.1, 0.9]) as predictor:
            response = self.client.post("/analyze/audio", content=make_audio(rate=48000, channels=2))
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["metadata"]["sample_rate"], 48000)
        self.assertEqual(result["metadata"]["channels"], 2)
        self.assertEqual(result["segments"][1]["start"], 6)
        self.assertEqual(result["segments"][1]["end"], 7.5)
        self.assertEqual(len(predictor.call_args_list[0].args[0]), 96000)
        self.assertEqual(result["audio_summary"]["scored_segments"], 2)
        self.assertEqual(result["audio_summary"]["flagged_segments"], 1)
        self.assertEqual(result["ai_score"], 0.9)
        self.assertEqual(result["verdict"], "audio_review_recommended")
        self.assertEqual(len(result["waveform"]), 160)

    def test_supported_compressed_formats(self):
        for fmt, codec in [("mp3", "libmp3lame"), ("flac", "flac"), ("mp4", "aac")]:
            with self.subTest(format=fmt), patch.object(audio, "predict", return_value=0.2):
                response = self.client.post("/analyze/audio", content=compressed_audio(fmt, codec))
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["model"]["status"], "completed")

    def test_silence_has_no_fabricated_score(self):
        with patch.object(audio, "predict") as predictor:
            response = self.client.post("/analyze/audio", content=make_audio(silent=True))
        self.assertEqual(response.status_code, 200, response.text)
        predictor.assert_not_called()
        self.assertIsNone(response.json()["ai_score"])
        self.assertEqual(response.json()["audio_summary"]["skipped_segments"], 2)

    def test_noise_is_skipped_by_voice_activity_check(self):
        with patch.object(audio, "predict") as predictor:
            result = self.client.post("/analyze/audio", content=make_audio(noise=True)).json()
        predictor.assert_not_called()
        self.assertEqual([segment["status"] for segment in result["segments"]], ["no_speech", "no_speech"])
        self.assertEqual(result["audio_summary"]["speech_segments"], 0)
        self.assertIsNone(result["ai_score"])
        voiced = audio.voiced_ratio((0.1 * np.sin(np.arange(16000) * 2 * np.pi * 180 / 16000)).astype(np.float32))
        self.assertGreater(voiced, 0.9)

    def test_short_tail_and_model_failure(self):
        with patch.object(audio, "predict", return_value=None):
            result = self.client.post("/analyze/audio", content=make_audio(seconds=6.5)).json()
        self.assertEqual(result["segments"][1]["status"], "too_short")
        self.assertIsNone(result["ai_score"])
        with patch.object(audio, "predict", side_effect=[RuntimeError("failed"), 0.1]), self.assertLogs("deepguard.audio", level="ERROR"):
            result = self.client.post("/analyze/audio", content=make_audio()).json()
        self.assertEqual(result["model"]["status"], "partial")
        self.assertEqual(result["verdict"], "inconclusive")

    def test_invalid_and_duration_limits(self):
        for content in [b"", b"#EXTM3U\nhttps://example.com/audio", make_audio(seconds=0.5), make_audio(seconds=121)]:
            self.assertEqual(self.client.post("/analyze/audio", content=content).status_code, 422)
        with patch.object(app, "MAX_AUDIO_BYTES", 10):
            self.assertEqual(self.client.post("/analyze/audio", content=make_audio()).status_code, 413)

    def test_timeout_and_busy(self):
        with patch.object(audio.subprocess, "run", side_effect=subprocess.TimeoutExpired("audio", 30)):
            self.assertEqual(self.client.post("/analyze/audio", content=make_audio()).status_code, 422)
        app.analysis_lock.acquire()
        try:
            self.assertEqual(self.client.post("/analyze/audio", content=b"audio").status_code, 429)
        finally:
            app.analysis_lock.release()


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--fixture":
        Path(sys.argv[2]).write_bytes(make_audio())
    else:
        unittest.main()
