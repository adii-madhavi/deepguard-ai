"""Optional API keys, per-client rate limits, and a bounded wait for the single analysis slot."""
import asyncio
from collections import defaultdict, deque
from contextlib import asynccontextmanager
import hmac
import os
import threading
import time

from fastapi import HTTPException, Request

API_KEYS = [key.strip() for key in os.getenv("DEEPGUARD_API_KEYS", "").split(",") if key.strip()]
RATE_LIMIT = int(os.getenv("DEEPGUARD_RATE_LIMIT", "0"))  # analyses per window per client IP; 0 disables
RATE_WINDOW = int(os.getenv("DEEPGUARD_RATE_WINDOW_SECONDS", "600"))
QUEUE_SIZE = int(os.getenv("DEEPGUARD_QUEUE_SIZE", "0"))  # requests allowed to wait for the busy slot
QUEUE_TIMEOUT = float(os.getenv("DEEPGUARD_QUEUE_TIMEOUT_SECONDS", "90"))
analysis_lock = threading.Lock()
_state_lock = threading.Lock()
_waiting = 0
_hits = defaultdict(deque)


def require_key(request: Request):
    if not API_KEYS:
        return
    supplied = request.headers.get("x-api-key") or request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if not any(hmac.compare_digest(supplied.encode(), key.encode()) for key in API_KEYS):
        raise HTTPException(401, "A valid API key is required.")


def rate_limit(request: Request):
    require_key(request)
    if RATE_LIMIT <= 0:
        return
    # ponytail: per-process memory; use Redis or the proxy's limiter when running several replicas.
    client = request.client.host if request.client else "unknown"
    now = time.monotonic()
    with _state_lock:
        if len(_hits) > 10000:
            for stale in [key for key, hits in _hits.items() if not hits or now - hits[-1] > RATE_WINDOW]:
                del _hits[stale]
        hits = _hits[client]
        while hits and now - hits[0] > RATE_WINDOW:
            hits.popleft()
        if len(hits) >= RATE_LIMIT:
            retry = int(RATE_WINDOW - (now - hits[0])) + 1
            raise HTTPException(429, f"Rate limit reached. Try again in {retry} seconds.", headers={"Retry-After": str(retry)})
        hits.append(now)


@asynccontextmanager
async def analysis_slot():
    """One analysis at a time; up to QUEUE_SIZE requests wait, the rest get 429."""
    global _waiting
    if not analysis_lock.acquire(blocking=False):
        with _state_lock:
            if _waiting >= QUEUE_SIZE:
                raise HTTPException(429, "Another file is being analyzed. Please try again shortly.")
            _waiting += 1
        try:
            # Polling (not a blocking thread) so a disconnected client can never strand the lock.
            # ponytail: not FIFO; use a real job queue when traffic needs fairness or multiple workers.
            deadline = time.monotonic() + QUEUE_TIMEOUT
            while not analysis_lock.acquire(blocking=False):
                if time.monotonic() > deadline:
                    raise HTTPException(503, "The analysis queue is busy. Please try again shortly.")
                await asyncio.sleep(0.2)
        finally:
            with _state_lock:
                _waiting -= 1
    try:
        yield
    finally:
        analysis_lock.release()
