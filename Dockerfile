FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    OCR_TEMP_DIR=/tmp/company_ocr_temp \
    TEMP_FILE_TTL_MINUTES=15 \
    PORT=8000

# Install system dependencies (Poppler, OpenCV runtime libraries, ZBar, curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    poppler-utils \
    libzbar0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root application user
RUN groupadd -g 10001 appuser && \
    useradd -u 10001 -g appuser -s /bin/bash -m appuser

WORKDIR /app

# Copy dependency specifications and install
COPY service_requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . /app/

# Create working directories and configure ownership for non-root user
RUN mkdir -p /app/uploads/original /app/uploads/processed /app/uploads/results /tmp/company_ocr_temp && \
    chown -R appuser:appuser /app /tmp/company_ocr_temp && \
    chmod -R 750 /app/uploads /tmp/company_ocr_temp

# Switch to non-root user
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["gunicorn", "-w", "2", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000", "--timeout", "300", "--access-logfile", "-", "--error-logfile", "-", "main:app"]
