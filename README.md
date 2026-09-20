# DeepGuard AI

Image-analysis MVP with a Next.js + Tailwind dashboard and a FastAPI inference service. Upload an image, inspect its metadata, view an AI-generation model score, and export a JSON report.

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

For metadata-only operation, install `backend/requirements.txt` and set `$env:DEEPGUARD_ENABLE_MODEL='0'` before starting the API. `.env.example` files document settings; the backend reads process environment variables, while Next.js can read `frontend/.env.local`.

## Features

- Responsive image dashboard with drag-and-drop, keyboard file selection, and preview.
- JPEG, PNG, and static WebP decoding, 10 MiB upload limit, and 20-megapixel image limit.
- Format, dimensions, color mode, EXIF count, software tag, and SHA-256 fingerprint.
- Local pretrained inference, inconclusive results, and downloadable JSON reports.
- Bounded in-flight analysis, restricted CORS, no application-level upload persistence.

## Model and interpretation

Uses [haywoodsloan/ai-image-detector-dev-deploy](https://huggingface.co/haywoodsloan/ai-image-detector-dev-deploy), an Apache-2.0 licensed SwinV2 classifier by Haywood Sloan. Its `artificial` label supplies the AI score. Weights are loaded as safetensors with remote code disabled and are not included in this repository.

Scores are **uncalibrated model outputs**, not confidence estimates. Provisional UI thresholds: >=0.8 for likely AI-generated, <=0.2 for likely natural, and inconclusive otherwise. These thresholds have not been validated on a representative deployment dataset. A low score does not establish authenticity. Screenshots, edits, recompression, and unfamiliar generators can produce false results.

Metadata and compression observations are descriptive and never used to invent manipulation percentages. This model does not localize face edits, verify provenance, or detect video/audio deepfakes. No accuracy claim is made for this application.

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

Video/frame analysis, audio detection, synchronization assessment, calibrated evaluation, and PostgreSQL report history are not implemented. Video and audio are labeled upcoming.

For public hosting, add authentication, infrastructure-level upload size/time limits and rate limiting, and a worker queue appropriate to traffic. The service currently supports local use and rejects concurrent analysis requests. Use Vercel for the frontend and a Python/container host with sufficient model RAM; set `NEXT_PUBLIC_API_URL` and `CORS_ORIGINS` to the actual domains. No deployment is created by this repository.
