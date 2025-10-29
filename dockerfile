# Playwright base includes Chromium and required libs (Cloud Run compatible)
FROM mcr.microsoft.com/playwright/python:v1.47.2-jammy

ENV PYTHONDONTWRITEBYTECODE=1 \
	PYTHONUNBUFFERED=1 \
	PORT=8080

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py scraper.py ./
COPY templates ./templates
COPY static ./static

# Launch with gunicorn; bind to $PORT (Cloud Run)
CMD ["bash", "-lc", "gunicorn -b 0.0.0.0:${PORT} -w 2 --threads 8 app:app"]
