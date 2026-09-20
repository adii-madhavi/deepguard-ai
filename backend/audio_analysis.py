"""Synthetic-speech signals with bounded decoding and explicit segment coverage."""
import json
import logging
import math
import os
from pathlib import Path
import subprocess
import sys
import threading

import numpy as np
from fastapi import HTTPException

MODEL_ID = os.getenv("DEEPGUARD_AUDIO_MODEL", "mo-thecreator/Deepfake-audio-detection")
MODEL_REVISION = os.getenv("DEEPGUARD_AUDIO_REVISION", "e4d9874b493362149cec96ced85f00b00b1a04c0")
SAMPLE_RATE = 16000
MAX_DURATION = 120
SEGMENT_SECONDS = 6
model_state = "loading"
detector = None
inference_lock = threading.Lock()
logger = logging.getLogger("deepguard.audio")


def load_detector():
    global detector, model_state
    if os.getenv("DEEPGUARD_ENABLE_AUDIO_MODEL", "1") == "0":
        model_state = "disabled"
        return
    try:
        from transformers import AutoFeatureExtractor, AutoModelForAudioClassification
        processor = AutoFeatureExtractor.from_pretrained(MODEL_ID, revision=MODEL_REVISION, trust_remote_code=False)
        model = AutoModelForAudioClassification.from_pretrained(
            MODEL_ID, revision=MODEL_REVISION, trust_remote_code=False, use_safetensors=True)
        labels = {int(key): value.lower() for key, value in model.config.id2label.items()}
        if set(labels.values()) != {"fake", "real"} or processor.sampling_rate != SAMPLE_RATE:
            raise ValueError("Expected fake/real labels and 16 kHz input")
        model.eval()
        detector = (processor, model, next(key for key, label in labels.items() if label == "fake"))
        model_state = "ready"
    except Exception:
        logger.exception("Audio detector unavailable")
        model_state = "unavailable"


def predict(samples):
    if detector is None:
        return None
    import torch
    processor, model, fake_index = detector
    with inference_lock, torch.inference_mode():
        inputs = processor(samples, sampling_rate=SAMPLE_RATE, return_tensors="pt")
        score = model(**inputs).logits.softmax(dim=-1)[0, fake_index].item()
    if not math.isfinite(score) or not 0 <= score <= 1:
        raise ValueError("Invalid audio model score")
    return score


def decode_audio(path: Path):
    import av
    with path.open("rb") as source:
        header = source.read(12)
    if header[:4] == b"RIFF" and header[8:12] == b"WAVE":
        fmt = "wav"
    elif header[:4] == b"fLaC":
        fmt = "flac"
    elif header[:3] == b"ID3" or (len(header) >= 2 and header[0] == 255 and header[1] & 224 == 224):
        fmt = "mp3"
    elif header[4:8] == b"ftyp":
        fmt = "mov"
    else:
        raise ValueError("Use a WAV, MP3, FLAC, or M4A audio file.")
    with av.open(str(path), format=fmt, options={"protocol_whitelist": "file", "enable_drefs": "0"}) as container:
        if container.streams.video or not container.streams.audio:
            raise ValueError("Upload an audio-only file with a readable audio track.")
        stream = container.streams.audio[0]
        rate, channels = stream.codec_context.sample_rate, stream.codec_context.channels
        if not 0 < rate <= 192000 or not 0 < channels <= 8:
            raise ValueError("Audio must have at most 8 channels and a sample rate of 192 kHz or less.")
        advertised = container.duration / av.time_base if container.duration else None
        if advertised and advertised > MAX_DURATION + 0.1:
            raise ValueError("Audio must be 120 seconds or shorter.")
        resampler = av.AudioResampler(format="fltp", layout="mono", rate=SAMPLE_RATE)
        chunks = []
        count = 0
        start_time = None
        last_end = None
        def append(frame):
            nonlocal count
            array = frame.to_ndarray().reshape(-1)
            count += len(array)
            if count > SAMPLE_RATE * MAX_DURATION:
                raise ValueError("Decoded audio exceeds 120 seconds.")
            if not np.isfinite(array).all():
                raise ValueError("Audio contains invalid sample values.")
            chunks.append(array)
        for frame in container.decode(stream):
            if frame.is_corrupt:
                raise ValueError("Audio contains a corrupt frame.")
            if frame.time is not None:
                if start_time is None:
                    start_time = frame.time
                if last_end is not None and abs(frame.time - last_end) > 0.1:
                    raise ValueError("Audio timestamps are discontinuous. Re-export the recording as WAV.")
                last_end = frame.time + frame.samples / frame.sample_rate
            for output in resampler.resample(frame):
                append(output)
        for output in resampler.resample(None):
            append(output)
        if count < SAMPLE_RATE:
            raise ValueError("Audio must contain at least one second of decoded samples.")
        samples = np.concatenate(chunks).astype(np.float32)
        np.save(path.parent / "samples.npy", samples, allow_pickle=False)
        return {"format": "M4A" if fmt == "mov" else fmt.upper(), "codec": stream.codec_context.name,
                "sample_rate": rate, "channels": channels, "analysis_sample_rate": SAMPLE_RATE,
                "duration_seconds": round(count / SAMPLE_RATE, 3), "audio_tracks": len(container.streams.audio)}


def analyze_audio(path: Path):
    try:
        worker = subprocess.run([sys.executable, str(Path(__file__).resolve()), str(path)],
                                capture_output=True, text=True, timeout=30, check=False,
                                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    except subprocess.TimeoutExpired:
        raise HTTPException(422, "Audio decoding exceeded 30 seconds. Try a smaller recording.") from None
    if worker.returncode != 0:
        raise HTTPException(422, "Audio could not be decoded. Try a WAV, MP3, FLAC, or M4A file.")
    try:
        metadata = json.loads(worker.stdout)
    except ValueError:
        raise HTTPException(422, "Audio decoding did not produce valid metadata.") from None
    if "error" in metadata:
        raise HTTPException(422, metadata["error"])
    samples = np.load(path.parent / "samples.npy", allow_pickle=False)
    segments = []
    for offset in range(0, len(samples), SAMPLE_RATE * SEGMENT_SECONDS):
        part = samples[offset:offset + SAMPLE_RATE * SEGMENT_SECONDS]
        rms = float(np.sqrt(np.mean(part.astype(np.float64) ** 2)))
        status = "too_short" if len(part) < SAMPLE_RATE else "near_silent" if rms < 0.001 else "unavailable"
        score = None
        if status == "unavailable":
            try:
                score = predict(part)
                if score is not None and (not math.isfinite(score) or not 0 <= score <= 1):
                    raise ValueError("Invalid model output")
                if score is not None:
                    status = "scored"
            except Exception:
                logger.exception("Audio segment inference failed")
                score = None
                status = "failed"
        segments.append({"start": round(offset / SAMPLE_RATE, 3),
                         "end": round((offset + len(part)) / SAMPLE_RATE, 3),
                         "ai_score": round(score, 6) if score is not None else None,
                         "flagged": score is not None and score >= 0.8, "status": status,
                         "rms_dbfs": round(20 * math.log10(max(rms, 1e-8)), 1)})
    waveform = [round(min(1.0, float(np.max(np.abs(part)))), 4)
                for part in np.array_split(samples, min(160, len(samples)))]
    scores = [segment["ai_score"] for segment in segments if segment["ai_score"] is not None]
    flagged = sum(segment["flagged"] for segment in segments)
    skipped = sum(segment["status"] in {"near_silent", "too_short"} for segment in segments)
    status = "completed" if len(scores) == len(segments) else "partial" if scores else "no_scores"
    return {
        "media_type": "audio", "metadata": metadata, "segments": segments, "waveform": waveform,
        "ai_score": max(scores) if scores else None,
        "verdict": "audio_review_recommended" if flagged else "inconclusive",
        "model": {"id": MODEL_ID, "revision": MODEL_REVISION, "status": status, "availability": model_state},
        "audio_summary": {"total_segments": len(segments), "scored_segments": len(scores),
                          "flagged_segments": flagged, "skipped_segments": skipped},
        "observations": [
            {"title": "Segment coverage", "value": f"{len(scores)} / {len(segments)} scored",
             "detail": "Non-overlapping six-second segments are analyzed. Segments under one second or below -60 dBFS RMS are left unscored."},
            {"title": "Analysis format", "value": "16 kHz mono",
             "detail": "The first audio track is downmixed and resampled for the speech classifier. Waveform and levels describe that signal."},
            {"title": "Near-full-scale samples", "value": f"{float(np.mean(np.abs(samples) >= 0.999)) * 100:.2f}%",
             "detail": "A descriptive level measurement after resampling; it is not evidence of synthetic speech."},
        ],
        "notes": [
            "The summary is the highest scored segment, not a calibrated confidence estimate for the recording.",
            "This experimental speech detector has limited published training documentation. Music, noise, unfamiliar languages, and new generators may produce unreliable results.",
            "No speech-activity detector is applied. A non-silent segment may contain music or noise rather than speech.",
            "Silence and short segments are not scored. Missing or low scores do not establish authenticity.",
            "Speaker identity, audio/video synchronization, and voice-clone attribution are not assessed.",
            "Uploaded audio and decoded samples use temporary files removed when the request completes.",
        ],
    }


if __name__ == "__main__":
    try:
        print(json.dumps(decode_audio(Path(sys.argv[1]))))
    except ValueError as error:
        print(json.dumps({"error": str(error)}))
