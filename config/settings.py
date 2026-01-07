"""
Django settings for config project.
Refactored for Production/Docker using python-decouple.
"""

from pathlib import Path

from decouple import Csv, config
from kombu import Queue

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# ==============================================================================
# SEGURANÇA E CONFIGURAÇÃO BÁSICA
# ==============================================================================
SECRET_KEY = config("SECRET_KEY", default="django-insecure-key-change-me")
DEBUG = config("DEBUG", default=False, cast=bool)

ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="*", cast=Csv())

# Importante para Django 4+ em produção (HTTPS)
CSRF_TRUSTED_ORIGINS = config(
    "CSRF_TRUSTED_ORIGINS", default="http://localhost,http://127.0.0.1", cast=Csv()
)

# ==============================================================================
# APLICAÇÃO DEFINITION
# ==============================================================================

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party / Libs
    "django_celery_results",
    "rest_framework",
    "drf_spectacular",
    "corsheaders",  # Recomendado se for usar API externamente
    # Apps Do sistema
    "apps.core",
    "apps.tenants",
    "apps.accounts",
    "apps.orders",
    "apps.integrations",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # Essencial para Docker
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",  # Se usar CORS
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.TenantMiddleware",  # Seu Middleware de Tenant
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],  # Usando Pathlib para ser mais seguro
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# ==============================================================================
# BANCO DE DADOS
# ==============================================================================
# Lógica: Usa SQLite se USE_SQLITE=True no .env, senão usa Postgres
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
            "USER": config("DB_USER", default="postgres"),
            "PASSWORD": config("DB_PASSWORD", default="postgres"),
            "HOST": config("DB_HOST", default="db"),
            "PORT": config("DB_PORT", default="5432"),
        }
    }

# Tipo de ID padrão para modelos (evita warnings)
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ==============================================================================
# PASSWORD VALIDATION & AUTH
# ==============================================================================

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# ==============================================================================
# INTERNATIONALIZATION & STATIC FILES
# ==============================================================================

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Locais adicionais de estáticos (ex: sua pasta 'static' na raiz)
STATICFILES_DIRS = [
    BASE_DIR / "static",
]

# Compressão eficiente para produção (WhiteNoise)
# Se der erro de "Missing File" no deploy, troque por:
# "whitenoise.storage.CompressedStaticFilesStorage"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Media files (Uploads)
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Auth
AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"  # Mudei para dashboard, faz mais sentido
LOGOUT_REDIRECT_URL = "login"


# ==============================================================================
# INTEGRAÇÕES & APIS
# ==============================================================================
# Evolution API (WhatsApp) - Configuração GLOBAL do sistema (vem do .env)
# Cada tenant só precisa informar o nome da instância
EVOLUTION_API_URL = config("EVOLUTION_API_URL", default="")
EVOLUTION_API_KEY = config("EVOLUTION_API_KEY", default="")


# ==============================================================================
# CELERY + REDIS
# ==============================================================================
CELERY_BROKER_URL = config("CELERY_BROKER_URL", default="redis://redis:6379/0")
CELERY_RESULT_BACKEND = config("CELERY_RESULT_BACKEND", default="redis://redis:6379/1")

CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE

# Otimizações do Celery
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1

# Filas separadas para prioridade (Opcional, mas bom para WhatsApp não travar relatórios)
CELERY_TASK_QUEUES = (
    Queue("default"),
    Queue("whatsapp"),
)

CELERY_TASK_ROUTES = {
    "apps.integrations.whatsapp.tasks.*": {"queue": "whatsapp"},
}


# ==============================================================================
# REST FRAMEWORK (Opcional - Configuração Básica)
# ==============================================================================
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
}


# ==============================================================================
# CELERY BEAT - TASKS PERIÓDICAS
# ==============================================================================
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    # Expira pedidos de retirada não realizados a cada hora
    "expire-pending-pickups": {
        "task": "apps.integrations.whatsapp.tasks.expire_pending_pickups",
        "schedule": crontab(minute=0),  # A cada hora cheia
    },
}


# ==============================================================================
# CONFIGURAÇÕES DO SITE
# ==============================================================================
SITE_URL = config("SITE_URL", default="http://localhost:8000")
