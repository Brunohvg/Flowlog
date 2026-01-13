"""
Django settings - Flowlog.
Production-ready for Docker Swarm.
"""

from pathlib import Path
from decouple import Csv, config

BASE_DIR = Path(__file__).resolve().parent.parent

# ==============================================================================
# SEGURANÇA
# ==============================================================================
SECRET_KEY = config("SECRET_KEY", default="django-insecure-change-me")
DEBUG = config("DEBUG", default=False, cast=bool)

# Em produção (DEBUG=False), ALLOWED_HOSTS deve ser explícito
# Em desenvolvimento (DEBUG=True), aceita localhost
_allowed_hosts = config("ALLOWED_HOSTS", default="", cast=Csv())
if DEBUG:
    ALLOWED_HOSTS = _allowed_hosts if _allowed_hosts else ["localhost", "127.0.0.1"]
else:
    # Em produção, não aceita "*" nem vazio
    if not _allowed_hosts or "*" in _allowed_hosts:
        ALLOWED_HOSTS = ["localhost"]  # Fallback seguro
    else:
        ALLOWED_HOSTS = _allowed_hosts

CSRF_TRUSTED_ORIGINS = config(
    "CSRF_TRUSTED_ORIGINS", default="http://localhost,http://127.0.0.1", cast=Csv()
)

# ==============================================================================
# APPS
# ==============================================================================
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_celery_results",
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    "corsheaders",
    "apps.core",
    "apps.tenants",
    "apps.accounts",
    "apps.orders",
    "apps.integrations",
    "apps.payments",
    "apps.api",
]

# ==============================================================================
# MIDDLEWARE
# ==============================================================================
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.TenantMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# ==============================================================================
# TEMPLATES
# ==============================================================================
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

# ==============================================================================
# DATABASE
# ==============================================================================
USE_SQLITE = config("USE_SQLITE", default=False, cast=bool)

if USE_SQLITE:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": config("DB_NAME", default="flowlog"),
            "USER": config("DB_USER", default="flowlog"),
            "PASSWORD": config("DB_PASSWORD", default=""),
            "HOST": config("DB_HOST", default="localhost"),
            "PORT": config("DB_PORT", default="5432"),
        }
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ==============================================================================
# AUTH
# ==============================================================================
AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

# ==============================================================================
# I18N / STATIC / MEDIA
# ==============================================================================
LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ==============================================================================
# CELERY
# ==============================================================================
CELERY_BROKER_URL = config("CELERY_BROKER_URL", default="")
CELERY_RESULT_BACKEND = config("CELERY_RESULT_BACKEND", default="")

if CELERY_BROKER_URL:
    from kombu import Queue
    
    # [CORREÇÃO] Habilita UTC explícito para alinhar Django <-> Celery
    CELERY_ENABLE_UTC = True
    CELERY_TIMEZONE = TIME_ZONE  # Mantém "America/Sao_Paulo" para agendamentos
    
    CELERY_ACCEPT_CONTENT = ["json"]
    CELERY_TASK_SERIALIZER = "json"
    CELERY_RESULT_SERIALIZER = "json"
    
    CELERY_TASK_ACKS_LATE = True
    CELERY_WORKER_PREFETCH_MULTIPLIER = 1
    
    CELERY_TASK_QUEUES = (
        Queue("default"),
        Queue("whatsapp"),
    )
    
    CELERY_TASK_ROUTES = {
        "apps.integrations.whatsapp.tasks.*": {"queue": "whatsapp"},
    }

# ==============================================================================
# SITE / EVOLUTION API
# ==============================================================================
SITE_URL = config("SITE_URL", default="http://localhost:8000")
EVOLUTION_API_URL = config("EVOLUTION_API_URL", default="")
EVOLUTION_API_KEY = config("EVOLUTION_API_KEY", default="")

# ==============================================================================
# LOGGING - STDOUT ONLY (Docker friendly)
# ==============================================================================
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {
            "format": "[{levelname}] {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "celery": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "apps": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}

# ==============================================================================
# DJANGO REST FRAMEWORK
# ==============================================================================
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

# ==============================================================================
# DRF SPECTACULAR (Swagger/OpenAPI)
# ==============================================================================
SPECTACULAR_SETTINGS = {
    "TITLE": "Flowlog API",
    "DESCRIPTION": "API REST para gestão de vendas via WhatsApp",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}