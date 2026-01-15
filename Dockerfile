FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN SECRET_KEY=build_secret \
    DEBUG=False \
    CELERY_BROKER_URL=redis://localhost:6379/0 \
    CELERY_RESULT_BACKEND=redis://localhost:6379/1 \
    python manage.py collectstatic --noinput || true

RUN adduser --disabled-password --no-create-home django-user && \
    chown -R django-user:django-user /app

USER django-user

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/healthcheck/ || exit 1

CMD ["gunicorn", "config.wsgi:application", "--bind=0.0.0.0:8000", "--workers=2", "--access-logfile=-", "--error-logfile=-"]
