# DeepGuard AI

Image, sampled-video, and segmented-audio analysis with a Next.js + Tailwind dashboard and a FastAPI inference service. Upload media, inspect metadata and model evidence, and export a JSON report.

## Run locally (PowerShell)

Requires Node.js 20.9+ and Python 3.11+.

```powershell
cd D:\deepguard-ai
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r backend/requirements-ml.txt
$env:HF_HOME='D:/deepguard-ai/models'
.venv/Scripts/python.exe -m uvicorn app:app --app-dir backend --host 127.0.0.1 --port 8000
```

In another terminal:

```powershell
cd D:\deepguard-ai\frontend
npm ci
npm run dev
```

Open http://localhost:3000. API documentation: http://127.0.0.1:8000/docs.

The model downloads from Hugging Face on first backend startup. The UI shows its loading state; metadata analysis remains available during loading or if inference dependencies are missing. Weights are cached by Hugging Face outside the repository. Set `HF_HOME` to choose another cache location.

For metadata-only operation, install `backend/requirements.txt` and set both `$env:DEEPGUARD_ENABLE_MODEL='0'` and `$env:DEEPGUARD_ENABLE_AUDIO_MODEL='0'` before starting the API. `.env.example` files document settings; the backend reads process environment variables, while Next.js can read `frontend/.env.local`.

## Features

- Responsive image/video dashboard with drag-and-drop, keyboard file selection, and preview.
- JPEG, PNG, and static WebP decoding, 10 MiB upload limit, and 20-megapixel image limit.
- Format, dimensions, color mode, EXIF count, software tag, and SHA-256 fingerprint.
- Local pretrained inference, inconclusive results, and downloadable JSON reports.
- MP4/MOV and WebM video uploads up to 100 MiB, 120 seconds, and 8,294,400 pixels per frame.
- Up to 12 evenly spaced video samples, per-frame model scores, basic OpenCV frontal-face boxes, filtering, and timestamp seeking.
- WAV, MP3, FLAC, and audio-only M4A uploads up to 50 MiB and 1–120 seconds, with waveform, six-second segment scores, playback seeking, and report export.
- Bounded in-flight analysis and restricted CORS. Images stay in memory; video/audio uploads and decoded data use temporary directories removed after success or failure.

## Audio analysis

The dedicated speech detector is [mo-thecreator/Deepfake-audio-detection](https://huggingface.co/mo-thecreator/Deepfake-audio-detection), credited to mo-thecreator and Abdalla312 and published under Apache-2.0. Revision `e4d9874b493362149cec96ced85f00b00b1a04c0` is pinned, the `fake` label is explicitly selected, and weights load as safetensors without remote code. The model downloads on startup alongside the image detector. `/health` exposes independent image and audio model states.

PyAV decodes the first audio track in a separate process with a 30-second timeout. Inputs are restricted to eight channels and 192 kHz or below, then downmixed to mono and resampled to 16 kHz. Decoded sample count enforces the duration limit independently of file metadata. Discontinuous timestamps are rejected so segment offsets remain aligned with playback.

Non-overlapping six-second segments are scored individually. Segments below one second or below -60 dBFS RMS are unscored, and failed/missing predictions remain absent. The summary is the maximum segment score. Scores >=0.8 trigger review; otherwise the result stays inconclusive. No confidence calibration or accuracy evaluation has been performed. The model's published training and intended-use documentation is limited. Music, noise, unfamiliar languages, and new generators may yield unreliable results. No speech-activity detector is used: non-silent does not necessarily mean speech.

Waveform and near-full-scale measurements describe the resampled mono signal and do not establish whether audio is synthetic. This version does not identify speakers or attribute voice clones. Video reports also analyze the first embedded audio track when it can be decoded. Frame and speech scores stay separate; they are never fused into a confidence percentage.

## Video analysis

The backend uses PyAV's bundled FFmpeg libraries to decode supported containers in a separate process with a 45-second decoding timeout. No standalone FFmpeg executable is required. Frames are resized to a maximum edge of 768 pixels before image-model inference; thumbnails are separate JPEG previews. Timestamps use presentation times relative to the selected video stream start.

The summary score is the **maximum scored sample**, not a whole-video probability. Samples at or above 0.8 are flagged for review. The overall result is review recommended if any sample is flagged and inconclusive otherwise, even when all scores are low. Missing model scores remain missing; the report shows partial coverage. Events between samples can be missed. OpenCV face boxes only locate likely frontal faces and do not assess manipulation or identity consistency.

Embedded audio is analyzed with the speech detector; an audio failure is recorded without discarding video results. Lip synchronization and temporal manipulation are not evaluated. Browser codec support may differ from backend support; if playback fails, sampled thumbnails and JSON results remain usable. Normal request completion and errors clean up temporary files; a hard machine/process crash can leave OS temporary files behind.

## Audio/video consistency

Video reports compare the first audio and video tracks' starts, ends, and durations. Timing comes from stream metadata, with a bounded packet-timestamp fallback where durations are missing (common with WebM). Missing or invalid evidence produces an unavailable result, not assumed alignment. A start or end difference greater than 250 ms is highlighted for manual review. Positive offsets mean audio starts or ends later than video.

These measurements describe track boundaries, **not lip-sync delay**. Intentional soundtracks, edits, container metadata, and codec padding can explain differences. Equal track boundaries cannot establish that speech matches visible mouth movement. Content-level lip synchronization requires a separate model and evaluation and remains unimplemented.

The combined report shows separate frame and embedded-speech scores and model details. A timing difference or flagged audio segment can recommend review without altering the visual model score. Audio segment times are relative to decoded audio; playback seeking adds its measured offset in the container. Frame timestamps use the container playback origin. If the audio offset cannot be determined, automatic audio seeking is disabled.

## Sampled temporal evidence

Video reports compare consecutive sampled frames after reducing each to a 64 × 64 grayscale signature. They show visual-change percentages, near-duplicate samples at or below 0.5%, strong visual changes at or above 24%, and the actual gaps between sample timestamps. This uses the same up-to-12 evenly spaced samples already decoded for visual analysis; it does not increase the upload, duration, or processing limits.

These are descriptive repetition and scene-change cues. Camera motion, low light, fades, compression, edits, and frame-rate conversion can produce the same patterns. The metric does not compare all frames, does not identify the cause of a change, and does not establish temporal manipulation or deepfake status.

## Model and interpretation

Uses [haywoodsloan/ai-image-detector-dev-deploy](https://huggingface.co/haywoodsloan/ai-image-detector-dev-deploy), an Apache-2.0 licensed SwinV2 classifier by Haywood Sloan. Its `artificial` label supplies the AI score. Weights are loaded as safetensors with remote code disabled and are not included in this repository.

Scores are **uncalibrated model outputs**, not confidence estimates. Provisional UI thresholds: >=0.8 for likely AI-generated, <=0.2 for likely natural, and inconclusive otherwise. These thresholds have not been validated on a representative deployment dataset. A low score does not establish authenticity. Screenshots, edits, recompression, and unfamiliar generators can produce false results.

Metadata and compression observations are descriptive and never used to invent manipulation percentages. The image model has not been validated on video deepfakes, does not localize face edits, and does not verify provenance. No accuracy claim is made for this application.

## Verification

```powershell
cd D:\deepguard-ai\backend
..\.venv\Scripts\python.exe -m unittest -v
cd ..\frontend
npm run build
npm exec playwright test
```

## Next stages

Browser tests require both local servers and Google Chrome. Verified with Node.js 24.19.0, Python 3.14.7, Next.js 16.3.5, and Transformers 4.57.6. Real CPU inference was smoke-tested; this is not an evaluation of detector accuracy. Model revision is pinned to `3824a1e5fb831d4347cb63dfcb3f2a752d987ef2`.

Content-level lip synchronization, temporal-consistency modeling, speech-activity detection, calibrated evaluation, and PostgreSQL report history remain future stages. To require actual image, video, and audio inference in browser tests, set `$env:REQUIRE_MODEL='1'` before running them. Browser tests run serially to respect the single-analysis service limit. Generated tone/shape fixtures verify software behavior, not detector accuracy.

For public hosting, add authentication, infrastructure-level upload size/time limits and rate limiting, and a worker queue appropriate to traffic. The service currently supports local use and rejects concurrent analysis requests. Use Vercel for the frontend and a Python/container host with sufficient model RAM; set `NEXT_PUBLIC_API_URL` and `CORS_ORIGINS` to the actual domains. No deployment is created by this repository.
