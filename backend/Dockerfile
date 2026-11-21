# CPU image for the API (Hugging Face Spaces Docker SDK, Render, Fly, etc.). Models download on first start.
FROM python:3.12-slim
RUN useradd -m -u 1000 user
WORKDIR /app
COPY requirements.txt requirements-ml.txt ./
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r requirements-ml.txt
COPY *.py ./
USER user
ENV HF_HOME=/home/user/.cache/huggingface \
    DEEPGUARD_DB=/home/user/data/reports.db \
    DEEPGUARD_RATE_LIMIT=20 \
    DEEPGUARD_QUEUE_SIZE=3 \
    PORT=7860
EXPOSE 7860
# --forwarded-allow-ips="*" trusts the host's proxy for client IPs (rate limiting); only expose behind that proxy.
CMD uvicorn app:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips="*"
