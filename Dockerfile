# Production Dockerfile for Smart Guided Troubleshooting Engine
FROM python:3.11-slim

WORKDIR /app

# Set environment variables for Python and offline model usage
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

# Install minimal system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt

# Copy schema and application code
COPY schema.py .
COPY app/ app/
COPY rules/ rules/
COPY data/ data/
COPY models/ models/
COPY cache/ cache/
COPY frontend/ frontend/

# Expose API port
EXPOSE 8000

# Health check verifies the pipeline is prewarmed and ready
HEALTHCHECK --interval=15s --timeout=10s --start-period=60s --retries=5 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start Uvicorn — binds 0.0.0.0 so cloud platforms can route traffic in
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
