"""Audio upload endpoint shares the application's single-analysis limit."""
import hashlib
from datetime import datetime, timezone
from pathlib import Path
import tempfile
from uuid import uuid4

from fastapi import HTTPException, Request
from starlette.concurrency import run_in_threadpool
import audio_analysis
from limits import analysis_slot


async def upload_audio(request: Request, max_bytes):
    async with analysis_slot():
        with tempfile.TemporaryDirectory(prefix="deepguard-audio-") as directory:
            path = Path(directory) / "upload.bin"
            size = 0
            digest = hashlib.sha256()
            with path.open("wb") as output:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > max_bytes:
                        raise HTTPException(413, "Audio must be 50 MB or smaller.")
                    output.write(chunk)
                    digest.update(chunk)
            if not size:
                raise HTTPException(422, "Choose an audio file to analyze.")
            report = await run_in_threadpool(audio_analysis.analyze_audio, path)
            report["metadata"]["size_bytes"] = size
            return {"id": str(uuid4()), "created_at": datetime.now(timezone.utc).isoformat(),
                    "sha256": digest.hexdigest(), **report}
