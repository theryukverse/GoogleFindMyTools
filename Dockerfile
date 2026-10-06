# Official slim Python base image
FROM python:3.12-slim

# OCI image labels
LABEL org.opencontainers.image.source="https://github.com/theryukverse/GoogleFindMyTools" \
      org.opencontainers.image.licenses="GPL-3.0" \
      org.opencontainers.image.description="Google Find My Device location tracker - self-hosted API & map UI"

# Container environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=UTC

WORKDIR /app

# Create non-root user and group
RUN groupadd -g 1000 appuser && \
    useradd -u 1000 -g appuser -m -s /bin/bash appuser

# Prepare data and application directories with non-root ownership
RUN mkdir -p /data /app && chown -R appuser:appuser /data /app

# Cache-friendly dependency installation
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source files
COPY --chown=appuser:appuser . /app/

# Switch to non-root user
USER appuser

# Expose single port for API and web UI
EXPOSE 8000

# Docker health check calling the health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; res = urllib.request.urlopen('http://localhost:8000/api/health'); exit(0 if res.getcode() == 200 else 1)"

# Process model: single process running poller, API, and static UI
CMD ["uvicorn", "tracker.main:app", "--host", "0.0.0.0", "--port", "8000"]
