# Build in CI or on a development machine. Production servers pull immutable images.
FROM node:22-slim AS web
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:0.11.15 AS uv
FROM python:3.12-slim AS dependencies
COPY --from=uv /uv /uvx /bin/
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --no-editable

FROM python:3.12-slim AS app-base
RUN groupadd --gid 10001 doaide && useradd --uid 10001 --gid 10001 --create-home doaide
WORKDIR /app
COPY --from=dependencies /app/.venv /app/.venv
COPY backend /app/backend
COPY scripts/backup.py scripts/encrypted_backup.py scripts/erase_workspace.py scripts/retention.py /app/scripts/
COPY docs/scopes /app/docs/scopes
COPY --from=web /build/dist /app/frontend/dist
RUN mkdir /data && chown doaide:doaide /data
ENV PATH="/app/.venv/bin:$PATH" DOAIDE_DB_PATH=/data/doaide.db PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER doaide
EXPOSE 8012
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8012/api/ready', timeout=3)"
CMD ["uvicorn","backend.main:app","--host","0.0.0.0","--port","8012"]

# Optional OCR worker image; keep OCR binaries out of the API runtime image.
FROM app-base AS ocr-worker
USER root
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr poppler-utils && rm -rf /var/lib/apt/lists/*
USER doaide
HEALTHCHECK NONE
CMD ["python","-m","backend.worker"]

# Default target is the API runtime, not the optional OCR worker.
FROM app-base AS runtime
