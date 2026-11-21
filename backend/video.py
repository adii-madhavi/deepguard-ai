"""Bounded video decoding in a subprocess; scoring stays in the model process."""
import base64
import io
import json
import logging
import math
from pathlib import Path
import subprocess
import sys

from fastapi import HTTPException
from PIL import Image
from av_timing import inspect_timing
import lipsync

logger = logging.getLogger("deepguard.video")

MAX_DURATION = 120
MAX_PIXELS = 3840 * 2160
SAMPLE_COUNT = 12
NEAR_DUPLICATE_PERCENT = 0.5
STRONG_CHANGE_PERCENT = 24


def decode_video(path: Path):
    import av
    import cv2
    import numpy as np

    with path.open("rb") as source:
        header = source.read(12)
    if header[4:8] == b"ftyp":
        container_format = "mov"
    elif header[:4] == b"\x1aE\xdf\xa3":
        container_format = "matroska"
    else:
        raise ValueError("Use an MP4, MOV, or WebM video.")
    face_detector = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    if face_detector.empty():
        raise RuntimeError("Face detector data unavailable")
    # Force a file-based container; never auto-detect playlists or network protocols.
    with av.open(str(path), format=container_format,
                 options={"protocol_whitelist": "file", "enable_drefs": "0"}) as container:
        if not container.streams.video:
            raise ValueError("The file has no video track.")
        stream = container.streams.video[0]
        stream.codec_context.thread_count = 2
        width, height = stream.codec_context.width, stream.codec_context.height
        if not 0 < width * height <= MAX_PIXELS:
            raise ValueError("Video resolution exceeds the 4K pixel limit.")
        duration = (float(stream.duration * stream.time_base) if stream.duration is not None
                    else float(container.duration / av.time_base) if container.duration else 0)
        if not math.isfinite(duration) or not 0 < duration <= MAX_DURATION:
            raise ValueError("Video must have a readable duration of 120 seconds or less.")
        start = float((stream.start_time or 0) * stream.time_base)
        origin = float(container.start_time / av.time_base) if container.start_time is not None else start
        origin = max(0.0, origin)
        timing = inspect_timing(container)
        fps = float(stream.average_rate) if stream.average_rate else None
        metadata = {
            "format": "MP4 / MOV" if container_format == "mov" else "WebM / Matroska",
            "width": width, "height": height, "color_mode": "RGB samples",
            "duration_seconds": round(duration, 3),
            "fps": round(fps, 3) if fps and math.isfinite(fps) else None,
            "codec": stream.codec_context.name, "has_audio": bool(container.streams.audio),
            "media_origin_seconds": origin, "audio_tracks": len(container.streams.audio),
            "software": str(container.metadata.get("encoder", ""))[:200] or None,
        }
        samples = []
        transitions = []
        previous_signature = None
        seen = set()
        for index in range(SAMPLE_COUNT):
            target = duration * index / SAMPLE_COUNT
            container.seek(int((start + target) / stream.time_base), stream=stream, backward=True)
            for decoded, frame in enumerate(container.decode(stream)):
                if decoded >= 600:
                    raise ValueError("Video has excessively long keyframe intervals.")
                if frame.time is None:
                    continue
                timestamp = float(frame.time) - start
                if not math.isfinite(timestamp) or timestamp < target - 0.001:
                    continue
                if frame.is_corrupt:
                    raise ValueError("Video contains a corrupt sampled frame.")
                if not 0 < frame.width * frame.height <= MAX_PIXELS:
                    raise ValueError("A frame exceeds the 4K pixel limit.")
                key = round(timestamp, 6)
                if key in seen:
                    break
                seen.add(key)
                image = frame.to_image().convert("RGB")
                image.thumbnail((768, 768))
                pixels = np.asarray(image)
                signature = cv2.resize(cv2.cvtColor(pixels, cv2.COLOR_RGB2GRAY), (64, 64), interpolation=cv2.INTER_AREA)
                change_percent = None
                if previous_signature is not None:
                    change_percent = float(np.abs(signature.astype(np.float32) - previous_signature).mean() / 255 * 100)
                    transitions.append(change_percent)
                previous_signature = signature
                boxes = face_detector.detectMultiScale(cv2.cvtColor(pixels, cv2.COLOR_RGB2GRAY),
                                                       scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
                faces = [{"x": round(int(x) / image.width, 4), "y": round(int(y) / image.height, 4),
                          "width": round(int(w) / image.width, 4), "height": round(int(h) / image.height, 4)}
                         for x, y, w, h in boxes]
                filename = f"frame-{len(samples):02d}.png"
                image.save(path.parent / filename)
                image.thumbnail((320, 320))
                thumbnail = io.BytesIO()
                image.save(thumbnail, format="JPEG", quality=75)
                image.close()
                samples.append({"timestamp": round(max(0, float(frame.time) - origin), 3), "file": filename,
                                "visual_change_percent": round(change_percent, 3) if change_percent is not None else None,
                                "near_duplicate_previous": change_percent is not None and change_percent <= NEAR_DUPLICATE_PERCENT,
                                "strong_visual_change": change_percent is not None and change_percent >= STRONG_CHANGE_PERCENT,
                                "faces": faces, "thumbnail": "data:image/jpeg;base64," +
                                base64.b64encode(thumbnail.getvalue()).decode("ascii")})
                break
        if not samples:
            raise ValueError("No readable video frames were found.")
        timestamps = [sample["timestamp"] for sample in samples]
        gaps = [right - left for left, right in zip(timestamps, timestamps[1:])]
        # ponytail: sampled-frame comparison only; decode all frames when a validated temporal model is available.
        temporal = {"status": "sampled", "sample_count": len(samples), "transition_count": len(transitions),
                    "near_duplicate_pairs": sum(value <= NEAR_DUPLICATE_PERCENT for value in transitions),
                    "strong_change_candidates": sum(value >= STRONG_CHANGE_PERCENT for value in transitions),
                    "median_change_percent": round(float(np.median(transitions)), 3) if transitions else None,
                    "max_change_percent": round(float(max(transitions)), 3) if transitions else None,
                    "median_timestamp_gap_seconds": round(float(np.median(gaps)), 3) if gaps else None,
                    "max_timestamp_gap_seconds": round(float(max(gaps)), 3) if gaps else None,
                    "near_duplicate_threshold_percent": NEAR_DUPLICATE_PERCENT,
                    "strong_change_threshold_percent": STRONG_CHANGE_PERCENT}
        first_face = next((sample["timestamp"] + origin for sample in samples if sample["faces"]), None)
        lip_sync = lipsync.measure(container, face_detector, first_face)
        return {"metadata": metadata, "frames": samples, "av_timing": timing, "temporal": temporal, "lip_sync": lip_sync}


def analyze_video(path: Path, predictor):
    try:
        worker = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), str(path)],
            capture_output=True, text=True, timeout=45, check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(422, "Video decoding exceeded 45 seconds. Try a shorter or smaller clip.") from None
    if worker.returncode != 0:
        raise HTTPException(422, "Video could not be decoded. Try an MP4, MOV, or WebM clip under two minutes.")
    try:
        decoded = json.loads(worker.stdout)
    except ValueError:
        raise HTTPException(422, "Video decoding did not produce a valid report.") from None
    if "error" in decoded:
        raise HTTPException(422, decoded["error"])
    for frame in decoded["frames"]:
        try:
            with Image.open(path.parent / frame.pop("file")) as image:
                score = predictor(image)
            if score is not None and (not math.isfinite(score) or not 0 <= score <= 1):
                score = None
        except Exception:
            logger.exception("Video frame inference failed")
            score = None
        frame["ai_score"] = round(score, 6) if score is not None else None
        frame["flagged"] = score is not None and score >= 0.8
    return decoded


if __name__ == "__main__":
    try:
        print(json.dumps(decode_video(Path(sys.argv[1]))))
    except ValueError as error:
        print(json.dumps({"error": str(error)}))
