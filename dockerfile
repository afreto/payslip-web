# syntax=docker/dockerfile:1

FROM python:3.11-slim

# Faster, cleaner Python & predictable port for Cloud Run
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080 \
    GUNICORN_CMD_ARGS='--workers=2 --threads=4 --timeout=120 --bind=0.0.0.0:${PORT}'

WORKDIR /app

# Minimal system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates tzdata curl \
 && rm -rf /var/lib/apt/lists/*

# Python deps first for better caching
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Install Playwright browser dependencies and Chromium for headless operation
RUN python -m playwright install --with-deps chromium

# App source
COPY . .

# Drop privileges
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Cloud Run will send traffic to $PORT; gunicorn serves Flask/FastAPI with '<your_main_file>:<your_app_object>'
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "main:application"]
