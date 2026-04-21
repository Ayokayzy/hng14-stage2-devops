# syntax=docker/dockerfile:1
FROM python:3.12-slim AS builder

WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim AS runtime

WORKDIR /app
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --gid 1000 workergroup \
    && useradd --uid 1000 --gid workergroup --shell /usr/sbin/nologin --no-create-home worker

COPY --from=builder /opt/venv /opt/venv
COPY worker.py .
RUN chown -R worker:workergroup /opt/venv /app

USER worker

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import os,redis;h=os.environ['REDIS_HOST'];p=int(os.environ['REDIS_PORT']);r=redis.Redis(host=h,port=p,socket_connect_timeout=3);r.ping()" || exit 1

CMD ["python", "-u", "worker.py"]
