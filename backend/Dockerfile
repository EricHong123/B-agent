FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    clamav \
    ffmpeg \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app

# Install Python dependencies. The vendored commerce packages arrive through the
# `commerce` build context (docker-compose `additional_contexts`) at /commerce, which
# is ../commerce from /app, as requirements.txt names them.
COPY --from=commerce . /commerce
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Create an unprivileged runtime identity. The clamav supplementary group can
# read the signature database mounted read-only by the media worker.
RUN groupadd --system app && \
    useradd --system --gid app --groups clamav --create-home app

# Copy application code
COPY --chown=app:app . .

# Create necessary directories
RUN mkdir -p uploads exports logs checkpoints && \
    chown -R app:app uploads exports logs checkpoints

USER app

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
