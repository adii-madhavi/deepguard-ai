"""Mouth-motion vs audio-energy correspondence: a descriptive lip-sync cue, not a trained sync model."""
import math

import numpy as np

WINDOW_SECONDS = 8
MAX_LAG_SECONDS = 0.5
MAX_FRAMES = 480
MIN_FACE_COVERAGE = 0.6
WEAK_CORRELATION = 0.2
OFFSET_REVIEW_SECONDS = 0.2


def correspondence(frame_times, motion, audio_times, audio_values, step):
    """Correlate per-frame mouth motion with log audio RMS shifted by each lag (positive = audio later)."""
    frame_times, motion = np.asarray(frame_times, float), np.asarray(motion, float)
    order = np.argsort(audio_times)
    audio_times, power = np.asarray(audio_times, float)[order], np.asarray(audio_values, float)[order] ** 2
    cumulative = np.concatenate([[0.0], np.cumsum(power)])
    valid = np.isfinite(motion)
    lags = range(-round(MAX_LAG_SECONDS / step), round(MAX_LAG_SECONDS / step) + 1)
    results = []
    for lag in lags:
        left = np.searchsorted(audio_times, frame_times + lag * step)
        right = np.searchsorted(audio_times, frame_times + (lag + 1) * step)
        counts = right - left
        energy = np.log10((cumulative[right] - cumulative[left]) / np.maximum(counts, 1) + 1e-10)
        usable = valid & (counts > 0)
        if usable.sum() < max(8, 2 / step) or np.std(motion[usable]) < 1e-9 or np.std(energy[usable]) < 1e-6:
            continue
        results.append((float(np.corrcoef(motion[usable], energy[usable])[0, 1]), lag * step))
    if not results:
        return None
    peak, offset = max(results)
    zero = next((value for value, lag in results if abs(lag) < step / 2), None)
    return {"best_offset_seconds": round(offset, 3), "peak_correlation": round(peak, 3),
            "zero_lag_correlation": round(zero, 3) if zero is not None else None}


def measure(container, face_detector, window_start):
    """Decode a dense window around the first face sample. window_start is presentation time in seconds."""
    import cv2

    result = {"status": "no_audio", "window_start_seconds": None, "window_seconds": None, "frames_analyzed": 0,
              "face_coverage": None, "best_offset_seconds": None, "peak_correlation": None,
              "zero_lag_correlation": None, "max_lag_seconds": MAX_LAG_SECONDS,
              "weak_correlation_threshold": WEAK_CORRELATION, "offset_review_seconds": OFFSET_REVIEW_SECONDS}
    if not container.streams.audio:
        return result
    if window_start is None:
        result["status"] = "no_face"
        return result
    video, audio = container.streams.video[0], container.streams.audio[0]
    end = window_start + WINDOW_SECONDS
    container.seek(int(window_start / video.time_base), stream=video, backward=True)
    times, motion, faces, previous, box = [], [], 0, None, None
    audio_times, audio_values = [], []
    done_video = False
    for packet in container.demux(video, audio):
        if packet.dts is None:
            continue
        if done_video and packet.pts is not None and packet.pts * packet.time_base > end + MAX_LAG_SECONDS + 1:
            break
        for frame in packet.decode():
            if frame.time is None:
                continue
            if packet.stream.type == "video":
                if frame.time >= end or len(times) >= MAX_FRAMES:
                    done_video = True
                if done_video or frame.time < window_start:
                    continue
                gray = frame.reformat(width=320, height=max(2, round(frame.height * 320 / frame.width)), format="gray").to_ndarray()
                if len(times) % 3 == 0:  # face boxes move slowly; re-detect every third frame
                    found = face_detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
                    box = max(found, key=lambda b: b[2] * b[3]) if len(found) else None
                mouth = None
                if box is not None:
                    x, y, w, h = (int(v) for v in box)
                    crop = gray[y + int(h * 0.65):y + int(h * 0.95), x + int(w * 0.2):x + int(w * 0.8)]
                    if crop.size:
                        mouth = cv2.resize(crop, (32, 16), interpolation=cv2.INTER_AREA).astype(np.float32)
                        faces += 1
                times.append(float(frame.time))
                motion.append(float(np.abs(mouth - previous).mean()) if mouth is not None and previous is not None else math.nan)
                previous = mouth
            elif window_start - MAX_LAG_SECONDS - 1 <= frame.time <= end + MAX_LAG_SECONDS + 1:
                samples = frame.to_ndarray().astype(np.float64)
                samples = samples.mean(axis=0) if frame.format.is_planar else samples.reshape(-1, len(frame.layout.channels)).mean(axis=1)
                audio_times.append(float(frame.time) + np.arange(len(samples)) / frame.sample_rate)
                audio_values.append(samples)
    result.update({"window_start_seconds": round(window_start, 3), "frames_analyzed": len(times)})
    if len(times) < 8:
        result["status"] = "insufficient_frames"
        return result
    step = float(np.median(np.diff(times)))
    result["window_seconds"] = round(times[-1] - times[0] + step, 3)
    result["face_coverage"] = round(faces / len(times), 3)
    if faces / len(times) < MIN_FACE_COVERAGE:
        result["status"] = "no_face"
        return result
    measured = correspondence(times, motion, np.concatenate(audio_times), np.concatenate(audio_values), step) if audio_values else None
    if measured is None:
        result["status"] = "low_activity"
        return result
    result.update(measured)
    result["status"] = ("weak_correspondence" if measured["peak_correlation"] < WEAK_CORRELATION
                        else "offset_candidate" if abs(measured["best_offset_seconds"]) > OFFSET_REVIEW_SECONDS
                        else "consistent_cue")
    return result
