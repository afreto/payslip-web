# 1.25.2
FROM mcr.microsoft.com/playwright/python:latest  

ENV PYTHONDONTWRITEBYTECODE=1 \
	PYTHONUNBUFFERED=1 \
	PORT=8080

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py scraper.py ./
COPY templates ./templates
COPY static ./static

#CMD ["bash", "-lc", "gunicorn -b 0.0.0.0:${PORT} -w 2 --threads 8 app:app"]
CMD ["bash", "-lc", "gunicorn -b 0.0.0.0:${PORT} -w 2 --threads 8 --access-logfile - --error-logfile - --log-level debug --capture-output app:app"]