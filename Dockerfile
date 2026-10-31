# ==========================================
# JESCA (Jessica Assets) v2.0 - Dockerfile
# ==========================================
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_APP=app.py

WORKDIR /app

# Install system dependencies (curl for healthcheck, git for self-update)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Ensure storage directories exist for persistence
RUN mkdir -p /app/data /app/static/uploads /app/static/attachments /app/backups

# Expose web application port
EXPOSE 5000

# Healthcheck targeting v2 /health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Volumes for persistent SQLite storage, uploads, attachments, and backups
VOLUME ["/app/data", "/app/static/uploads", "/app/static/attachments", "/app/backups"]

# Run application using Gunicorn with custom config
CMD ["gunicorn", "-c", "gunicorn.conf.py", "app:app"]
