FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv (The Modern Python Package Manager)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# Copy dependency files
COPY pyproject.toml requirements.txt ./

# Install dependencies using uv (Fast & Reliable)
# We use --system to install into the system python (no venv needed in container)
RUN uv pip install -r requirements.txt

# Copy entrypoint script and make it executable
COPY docker-entrypoint.sh /usr/local/bin/
# Set permissions (Keep as root for volume compatibility like v1.9)
RUN chmod +x /usr/local/bin/docker-entrypoint.sh
COPY . .

# Expose port
EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/healthcheck/ || exit 1

# Set the entrypoint
ENTRYPOINT ["docker-entrypoint.sh"]

# Default command
CMD ["gunicorn", "config.wsgi:application", "--bind=0.0.0.0:8000", "--workers=2", "--threads=4", "--timeout=60", "--access-logfile=-", "--error-logfile=-"]
