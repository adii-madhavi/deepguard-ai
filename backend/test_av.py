"""Timing evidence and combined inference on generated containers."""
import os
os.environ["DEEPGUARD_ENABLE_MODEL"] = "0"
os.environ["DEEPGUARD_ENABLE_AUDIO_MODEL"] = "0"
from fractions import Fraction
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import av
import numpy as np
from fastapi import HTTPException
from fastapi.testclient import TestClient
import app
import audio_analysis
from av_timing import compare_tracks
import lipsync


def make_av_clip(offset=1.0, duration=3, fmt="mp4"):
    buffer = io.BytesIO()
    with av.open(buffer, "w", format=fmt) as output:
        video = output.add_stream("libx264" if fmt == "mp4" else "libvpx-vp9", rate=12)
        video.width, video.height, video.pix_fmt = 160, 96, "yuv420p"
        audio = output.add_stream("aac" if fmt == "mp4" else "libopus", rate=16000)
        audio.layout = "mono"
        packets = []
        for index in range(duration * 12):
            pixels = np.zeros((96,160,3), dtype=np.uint8)
            pixels[:,:,1] = 80
            pixels[20:60, index % 100:index % 100 + 30] = [170,120,40]
            frame = av.VideoFrame.from_ndarray(pixels, format="rgb24")
            frame.pts, frame.time_base = index, Fraction(1,12)
            packets.extend(video.encode(frame))
        packets.extend(video.encode())
        count = int((duration - offset) * 16000)
        for index in range(0, count, 1024):
            samples = (0.1 * np.sin(np.arange(index,min(index+1024,count)) * 2 * np.pi * 220 / 16000)).astype(np.float32)
            frame = av.AudioFrame.from_ndarray(samples.reshape(1,-1), format="fltp", layout="mono")
            frame.sample_rate, frame.time_base = 16000, Fraction(1,16000)
            frame.pts = int(offset * 16000) + index
            packets.extend(audio.encode(frame))
        packets.extend(audio.encode())
        for packet in sorted(packets, key=lambda p: float((p.dts or 0) * p.time_base)):
            output.mux(packet)
    return buffer.getvalue()


def make_talking_clip(audio_delay, seconds=6, fps=25):
    """Mouth stripes flicker during 'talking' blocks; audio is loud in the same blocks, delayed by audio_delay."""
    talking = np.repeat(np.random.default_rng(2).integers(0, 2, seconds * 5), fps // 5)
    buffer = io.BytesIO()
    with av.open(buffer, "w", format="mp4") as output:
        video = output.add_stream("libx264", rate=fps)
        video.width, video.height, video.pix_fmt = 160, 96, "yuv420p"
        audio = output.add_stream("aac", rate=16000)
        audio.layout = "mono"
        packets = []
        for index in range(seconds * fps):
            pixels = np.full((96, 160, 3), 90, dtype=np.uint8)
            if talking[index] and index % 2:
                pixels[60:90:4, 50:110] = 240
            frame = av.VideoFrame.from_ndarray(pixels, format="rgb24")
            frame.pts, frame.time_base = index, Fraction(1, fps)
            packets.extend(video.encode(frame))
        packets.extend(video.encode())
        t = np.arange(seconds * 16000) / 16000
        gain = np.where(talking[np.clip(((t - audio_delay) * fps).astype(int), 0, len(talking) - 1)] & (t >= audio_delay), 0.3, 0.003)
        signal = (gain * np.sin(t * 2 * np.pi * 220)).astype(np.float32)
        for index in range(0, len(signal), 1024):
            frame = av.AudioFrame.from_ndarray(signal[index:index + 1024].reshape(1, -1), format="fltp", layout="mono")
            frame.sample_rate, frame.time_base, frame.pts = 16000, Fraction(1, 16000), index
            packets.extend(audio.encode(frame))
        packets.extend(audio.encode())
        for packet in sorted(packets, key=lambda p: float((p.dts or 0) * p.time_base)):
            output.mux(packet)
    return buffer.getvalue()


class AVTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app.app)

    def test_timing_decisions(self):
        track = {"start_seconds":0.0,"duration_seconds":3.0}
        self.assertEqual(compare_tracks(track, None)["status"], "no_audio")
        self.assertEqual(compare_tracks(track, {"start_seconds":None,"duration_seconds":3})["status"], "unavailable")
        self.assertEqual(compare_tracks(track, track)["status"], "boundaries_aligned")
        shorter = compare_tracks(track, {"start_seconds":0.0,"duration_seconds":2.0})
        self.assertEqual(shorter["status"], "timing_difference")
        self.assertEqual(shorter["end_offset_seconds"], -1)

    def test_real_shifted_audio_and_separate_scores(self):
        with patch.object(app, "predict", return_value=0.1), patch.object(audio_analysis, "predict", return_value=0.95):
            response = self.client.post("/analyze/video", content=make_av_clip())
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["av_timing"]["status"], "timing_difference")
        self.assertAlmostEqual(result["av_timing"]["start_offset_seconds"], 1.0, delta=0.1)
        self.assertAlmostEqual(result["embedded_audio"]["playback_offset_seconds"], 1.0, delta=0.1)
        self.assertEqual(result["ai_score"], 0.1)
        self.assertEqual(result["embedded_audio"]["ai_score"], 0.95)
        self.assertEqual(result["verdict"], "av_review_recommended")
        self.assertEqual(result["lip_sync"]["status"], "no_face")

    def test_lip_sync_correspondence_finds_offset(self):
        rng = np.random.default_rng(1)
        talking = np.repeat(rng.integers(0, 2, 40), 5).astype(float)  # 8 s of 0.2 s talk/quiet blocks at 25 fps
        times = np.arange(len(talking)) / 25
        audio_times = np.arange(int(8.6 * 16000)) / 16000 - 0.3
        envelope = 0.01 + talking[np.clip(((audio_times - 0.3) * 25).astype(int), 0, len(talking) - 1)]
        measured = lipsync.correspondence(times, talking, audio_times, envelope * rng.standard_normal(len(audio_times)), 0.04)
        self.assertAlmostEqual(measured["best_offset_seconds"], 0.3, delta=0.041)
        self.assertGreater(measured["peak_correlation"], 0.8)
        self.assertLess(measured["zero_lag_correlation"], measured["peak_correlation"])
        self.assertIsNone(lipsync.correspondence(times, np.zeros(len(times)), audio_times, envelope, 0.04))

    def test_lip_sync_measure_on_decoded_clip(self):
        class Face:
            def detectMultiScale(self, *args, **kwargs):
                return [(80, 20, 160, 160)]  # in the 320-wide analysis frame
        with av.open(io.BytesIO(make_talking_clip(0.3))) as container:
            result = lipsync.measure(container, Face(), 0.0)
        self.assertEqual(result["face_coverage"], 1.0)
        self.assertEqual(result["status"], "offset_candidate")
        self.assertAlmostEqual(result["best_offset_seconds"], 0.3, delta=0.09)
        with av.open(io.BytesIO(make_talking_clip(0.0))) as container:
            self.assertEqual(lipsync.measure(container, Face(), 0.0)["status"], "consistent_cue")

    def test_embedded_failure_preserves_video(self):
        with patch.object(app, "predict", return_value=0.1), patch.object(audio_analysis, "analyze_audio", side_effect=HTTPException(422,"Audio unavailable")):
            response = self.client.post("/analyze/video", content=make_av_clip(offset=0))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["av_timing"]["status"], "boundaries_aligned")
        self.assertEqual(len(response.json()["frames"]), 12)
        self.assertEqual(response.json()["embedded_audio"]["error"], "Audio unavailable")

    def test_webm_packet_timing_and_embedded_audio(self):
        with patch.object(app, "predict", return_value=0.1), patch.object(audio_analysis, "predict", return_value=0.1):
            response = self.client.post("/analyze/video", content=make_av_clip(offset=0,fmt="webm"))
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["av_timing"]["status"], "boundaries_aligned")
        self.assertEqual(result["av_timing"]["video"]["source"], "packet_timestamps")
        self.assertEqual(result["embedded_audio"]["model"]["status"], "completed")

    def test_audio_endpoint_still_rejects_video(self):
        response = self.client.post("/analyze/audio", content=make_av_clip())
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--fixture":
        Path(sys.argv[2]).write_bytes(make_av_clip(duration=8))
    else:
        unittest.main()
