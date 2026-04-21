# syntax=docker/dockerfile:1
FROM python:3.12-slim AS builder

WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip==24.3.1 \
    && pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim AS runtime

WORKDIR /app
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --gid 1000 appgroup \
    && useradd --uid 1000 --gid appgroup --shell /usr/sbin/nologin --no-create-home appuser

COPY --from=builder /opt/venv /opt/venv
COPY main.py .
RUN chown -R appuser:appgroup /opt/venv /app

USER appuser

ENV UVICORN_PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import os, urllib.request; p=os.environ.get('UVICORN_PORT','8000'); urllib.request.urlopen(f'http://127.0.0.1:{p}/openapi.json', timeout=4)" || exit 1

CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port \"${UVICORN_PORT}\""]
