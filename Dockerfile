FROM python:3.13-slim

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ffmpeg \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Install gunicorn along with other requirements
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Non-root user
RUN addgroup --system app && adduser --system --ingroup app app

# Create upload dir
RUN mkdir -p /app/temporary_uploads \
 && chown -R app:app /app/temporary_uploads

COPY --chown=app:app . .

USER app

EXPOSE 8080

# Use Gunicorn to start ONE worker process. This is stable for production.
# It will run the 'app' object inside your 'app.py' file.
CMD ["gunicorn", "--workers", "1", "--bind", "0.0.0.0:8080", "--timeout", "900", "app:app"]