"""
Configuração principal do Celery.
Configurado para não tentar conectar se CELERY_BROKER_URL não estiver definido.
"""

import os

from celery import Celery
from decouple import config

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("flowlog")

# Só configura conexão real se tiver broker
broker_url = config("CELERY_BROKER_URL", default="")
if broker_url:
    app.config_from_object("django.conf:settings", namespace="CELERY")
    app.autodiscover_tasks()
else:
    # Sem broker - configura para não tentar conectar
    app.conf.update(
        broker_url=None,
        result_backend=None,
        task_always_eager=False,
    )
