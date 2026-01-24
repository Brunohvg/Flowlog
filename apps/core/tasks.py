import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone
from django_celery_results.models import TaskResult

logger = logging.getLogger(__name__)


@shared_task(name="apps.core.tasks.cleanup_celery_results")
def cleanup_celery_results(days=7):
    """
    Limpa resultados antigos do Celery para evitar que a tabela TaskResult
    cresça indefinidamente e degrade a performance do banco de dados.
    """
    threshold = timezone.now() - timedelta(days=days)
    deleted_count, _ = TaskResult.objects.filter(date_done__lt=threshold).delete()

    if deleted_count > 0:
        logger.info(
            f"[Cleanup] Removidos {deleted_count} resultados de tasks anteriores a {threshold.date()}."
        )
    return deleted_count
