# ==============================================================================
# Build Stage
# ==============================================================================
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install build dependencies if needed (e.g., for pandas/numpy compilation)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set up virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ==============================================================================
# Runner Stage
# ==============================================================================
FROM python:3.11-slim AS runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PMS_DATA_DIR="/app/data" \
    PMS_DEFAULT_FILE_PATH="/app/data/PMS_Trend_All.xlsx" \
    PORT=7860

WORKDIR /app

# Copy virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv

# Create a non-privileged user and group
RUN groupadd -g 10001 pmsgroup && \
    useradd -u 10001 -g pmsgroup -d /app -s /sbin/nologin pmsuser

# Copy application files (with correct ownership)
COPY --chown=pmsuser:pmsgroup . .

# Create persistent data directory and set permissions
RUN mkdir -p /app/data && chown -R pmsuser:pmsgroup /app/data

# Switch to non-root user
USER pmsuser

# Expose port
EXPOSE 7860

# Health check using the platform-provided PORT (eliminating curl dependency)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://localhost:%s/api/health/liveness' % os.getenv('PORT', '7860'))"

# Start FastAPI application on the hosting platform's assigned port
CMD ["sh", "-c", "exec uvicorn app:app --host 0.0.0.0 --port ${PORT:-7860}"]
