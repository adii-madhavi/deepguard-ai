"""Images stay in memory; video temporary files are removed after each request."""
import hashlib
import io
import logging
import math
import os
from pathlib import Path
import tempfile
import threading
import warnings
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool

MAX_BYTES = 10 * 1024 * 1024
MAX_VIDEO_BYTES = 100 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 20_000_000
MODEL_ID = os.getenv("DEEPGUARD_MODEL", "haywoodsloan/ai-image-detector-dev-deploy")
MODEL_REVISION = os.getenv("DEEPGUARD_REVISION", "3824a1e5fb831d4347cb63dfcb3f2a752d987ef2")
AI_LABEL = os.getenv("DEEPGUARD_AI_LABEL", "artificial").lower()
logger = logging.getLogger("deepguard")
detector = None
model_state = "loading"
inference_lock = threading.Lock()
analysis_lock = threading.Lock()


def load_detector():
    global detector, model_state
    if os.getenv("DEEPGUARD_ENABLE_MODEL", "1") == "0":
        model_state = "disabled"
        return
    try:
        from transformers import AutoImageProcessor, AutoModelForImageClassification
        processor = AutoImageProcessor.from_pretrained(MODEL_ID, revision=MODEL_REVISION, trust_remote_code=False)
        model = AutoModelForImageClassification.from_pretrained(
            MODEL_ID, revision=MODEL_REVISION, trust_remote_code=False, use_safetensors=True
        )
        labels = {int(k): v.lower() for k, v in model.config.id2label.items()}
        if AI_LABEL not in labels.values() or len(labels) != 2:
            raise ValueError("Expected a binary classifier with the configured AI label")
        model.eval()
        detector = (processor, model, labels)
        model_state = "ready"
    except Exception:
        logger.exception("Detector unavailable; metadata analysis remains enabled")
        model_state = "unavailable"


@asynccontextmanager
async def lifespan(app):
    threading.Thread(target=load_detector, daemon=True).start()
    yield


app = FastAPI(title="DeepGuard AI", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/health")
def health():
    return {"status": "ok", "model_status": model_state, "model_id": MODEL_ID}


def predict(image):
    if detector is None:
        return None
    import torch
    processor, model, labels = detector
    with inference_lock, torch.inference_mode():
        inputs = processor(images=image, return_tensors="pt")
        scores = model(**inputs).logits.softmax(dim=-1)[0].tolist()
    score = next(scores[index] for index, label in labels.items() if label == AI_LABEL)
    if not math.isfinite(score) or not 0 <= score <= 1:
        raise ValueError("Invalid model score")
    return score


def analyze(data: bytes):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if source.format not in {"JPEG", "PNG", "WEBP"}:
                    raise HTTPException(415, "Use a JPEG, PNG, or WebP image.")
                if getattr(source, "n_frames", 1) != 1:
                    raise HTTPException(415, "Animated images are not supported in this version.")
                source.verify()
            with Image.open(io.BytesIO(data)) as source:
                source.load()
                exif = source.getexif()
                metadata = {"format": source.format, "width": source.width, "height": source.height,
                            "color_mode": source.mode, "size_bytes": len(data), "exif_fields": len(exif),
                            "software": str(exif.get(305, ""))[:200] or None}
                image = ImageOps.exif_transpose(source).convert("RGB")
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        raise HTTPException(422, "This file is not a readable image.") from None
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(413, "Image exceeds the 20 megapixel limit.") from None

    notes = ["Model scores are uncalibrated signals, not probabilities of authenticity.",
             "This image classifier does not locate face edits or establish provenance."]
    try:
        score = predict(image)
    except Exception:
        logger.exception("Inference failed")
        score = None
        notes.append("The detector could not complete this analysis.")
    finally:
        image.close()
    verdict = "inconclusive"
    if score is not None:
        verdict = "likely_ai_generated" if score >= 0.8 else "likely_natural" if score <= 0.2 else "inconclusive"
    else:
        notes.append("Model unavailable or still loading; only metadata was inspected.")
    return {
        "id": str(uuid4()), "created_at": datetime.now(timezone.utc).isoformat(),
        "sha256": hashlib.sha256(data).hexdigest(), "verdict": verdict,
        "ai_score": round(score, 6) if score is not None else None,
        "model": {"id": MODEL_ID, "revision": MODEL_REVISION, "status": "completed" if score is not None else model_state},
        "metadata": metadata, "notes": notes,
        "observations": [
            {"title": "Embedded metadata", "value": f"{len(exif)} EXIF fields",
             "detail": "Metadata can be removed or modified. Its presence or absence does not prove authenticity."},
            {"title": "Encoding", "value": metadata["format"],
             "detail": "Compression is common in both camera images and generated media; no manipulation score is inferred."},
            {"title": "Image integrity", "value": "Readable",
             "detail": "The file decodes successfully. This checks file integrity, not whether the scene is real."}
        ],
    }


@app.post("/analyze")
async def analyze_upload(request: Request):
    # ponytail: one in-flight analysis per process; add a bounded worker queue when traffic requires it.
    if not analysis_lock.acquire(blocking=False):
        raise HTTPException(429, "Another image is being analyzed. Please try again shortly.")
    try:
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > MAX_BYTES:
                raise HTTPException(413, "Image must be 10 MB or smaller.")
            data.extend(chunk)
        if not data:
            raise HTTPException(422, "Choose an image to analyze.")
        return await run_in_threadpool(analyze, bytes(data))
    finally:
        analysis_lock.release()


@app.post("/analyze/video")
async def analyze_video_upload(request: Request):
    from video import analyze_video

    if not analysis_lock.acquire(blocking=False):
        raise HTTPException(429, "Another file is being analyzed. Please try again shortly.")
    try:
        # TemporaryDirectory removes uploaded bytes and extracted frames on success or error.
        with tempfile.TemporaryDirectory(prefix="deepguard-video-") as directory:
            path = Path(directory) / "upload.bin"
            digest = hashlib.sha256()
            size = 0
            with path.open("wb") as output:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > MAX_VIDEO_BYTES:
                        raise HTTPException(413, "Video must be 100 MB or smaller.")
                    output.write(chunk)
                    digest.update(chunk)
            if not size:
                raise HTTPException(422, "Choose a video to analyze.")
            analysis = await run_in_threadpool(analyze_video, path, predict)
            frames = analysis["frames"]
            scores = [frame["ai_score"] for frame in frames if frame["ai_score"] is not None]
            flagged = sum(frame["flagged"] for frame in frames)
            status = "completed" if len(scores) == len(frames) else "partial" if scores else "unavailable"
            analysis["metadata"]["size_bytes"] = size
            return {
                "id": str(uuid4()), "created_at": datetime.now(timezone.utc).isoformat(),
                "media_type": "video", "sha256": digest.hexdigest(),
                "verdict": "review_recommended" if flagged else "inconclusive",
                "ai_score": max(scores) if scores else None,
                "model": {"id": MODEL_ID, "revision": MODEL_REVISION, "status": status},
                **analysis,
                "summary": {"sampled_frames": len(frames), "scored_frames": len(scores),
                            "flagged_frames": flagged, "frames_with_faces": sum(bool(f["faces"]) for f in frames)},
                "observations": [
                    {"title": "Sample coverage", "value": f"{len(frames)} frames",
                     "detail": "Up to 12 evenly spaced timestamps were inspected. Events between samples may be missed."},
                    {"title": "Face observations", "value": f"{sum(bool(f['faces']) for f in frames)} samples with faces",
                     "detail": "OpenCV frontal-face detections can miss faces or produce false positives. They do not indicate manipulation."},
                    {"title": "Audio track", "value": "Present" if analysis["metadata"]["has_audio"] else "Not present",
                     "detail": "Audio contents and audio/video synchronization were not analyzed."},
                ],
                "notes": [
                    "The displayed score is the highest uncalibrated image-detector score among sampled frames, not a whole-video probability.",
                    "This image model has not been validated for video deepfakes. No face-manipulation or temporal-consistency verdict is produced.",
                    "Frame images are resized to a maximum edge of 768 pixels before scoring. Display thumbnails are JPEG previews.",
                    f"{len(scores)} of {len(frames)} sampled frames received model scores. Missing scores are never counted as natural.",
                    "Uploaded video and extracted frames are temporarily written to disk and deleted after the request completes.",
                ],
            }
    finally:
        analysis_lock.release()
