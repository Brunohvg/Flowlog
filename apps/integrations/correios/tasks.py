"""
Tasks Celery para integração com os Correios.
"""

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(
    name="poll_correios_tracking",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    rate_limit="3/s",  # Limite de 3 requisições/segundo da API Correios
)
def poll_correios_tracking(self, tenant_id: int = None):
    """
    Task para polling de rastreio dos Correios.

    Consulta pedidos com delivery_type SEDEX/PAC que estão em trânsito
    e atualiza seus status baseado na API dos Correios.

    Args:
        tenant_id: ID do tenant específico (opcional). Se None, processa todos.
    """
    from apps.orders.models import Order, DeliveryStatus, DeliveryType
    from apps.tenants.models import Tenant
    from apps.integrations.correios.services import process_correios_tracking

    logger.info("Iniciando polling de rastreio Correios")

    # Filtrar tenants
    if tenant_id:
        tenants = Tenant.objects.filter(id=tenant_id, is_active=True)
    else:
        tenants = Tenant.objects.filter(is_active=True)

    total_processed = 0
    total_updated = 0

    for tenant in tenants:
        try:
            settings = tenant.settings
        except Exception:
            continue

        if not settings.correios_enabled:
            continue

        # Buscar pedidos em trânsito dos Correios
        orders = Order.objects.filter(
            tenant=tenant,
            delivery_type__in=[DeliveryType.SEDEX, DeliveryType.PAC],
            delivery_status__in=[
                DeliveryStatus.PENDING,
                DeliveryStatus.SHIPPED,
                DeliveryStatus.FAILED_ATTEMPT,
            ],
        ).exclude(
            tracking_code="",
        ).exclude(
            tracking_code__isnull=True,
        ).order_by("last_tracking_check")  # Priorizar os não verificados recentemente

        # Filtrar por frequência de verificação
        # - Shipped recente: a cada 4 horas
        # - Shipped antigo (>3 dias): a cada 12 horas
        # - Failed attempt: a cada 6 horas
        now = timezone.now()

        for order in orders[:50]:  # Limitar batch por execução
            should_check = False

            if not order.last_tracking_check:
                should_check = True
            elif order.delivery_status == DeliveryStatus.PENDING:
                # Pendente: verificar a cada 8 horas
                should_check = now - order.last_tracking_check > timedelta(hours=8)
            elif order.delivery_status == DeliveryStatus.FAILED_ATTEMPT:
                # Falha: verificar mais frequentemente
                should_check = now - order.last_tracking_check > timedelta(hours=6)
            elif order.shipped_at:
                days_since_shipped = (now - order.shipped_at).days
                if days_since_shipped < 3:
                    # Recente: verificar a cada 4 horas
                    should_check = now - order.last_tracking_check > timedelta(hours=4)
                else:
                    # Antigo: verificar menos frequentemente
                    should_check = now - order.last_tracking_check > timedelta(hours=12)
            else:
                should_check = now - order.last_tracking_check > timedelta(hours=8)

            if not should_check:
                continue

            try:
                result = process_correios_tracking(order)
                total_processed += 1

                if result.get("processed"):
                    total_updated += 1
                    logger.info(
                        "Pedido %s atualizado: %s",
                        order.code, result.get("new_status")
                    )

            except Exception as e:
                logger.exception(
                    "Erro ao processar rastreio do pedido %s: %s",
                    order.code, e
                )

    logger.info(
        "Polling Correios concluído: %d processados, %d atualizados",
        total_processed, total_updated
    )

    return {
        "processed": total_processed,
        "updated": total_updated,
    }


@shared_task(name="refresh_correios_token")
def refresh_correios_token(tenant_id: int):
    """
    Task para renovar token de autenticação dos Correios.

    Chamada automaticamente quando o token está próximo de expirar.
    """
    from apps.tenants.models import Tenant
    from apps.integrations.correios.services import get_correios_client

    try:
        tenant = Tenant.objects.get(id=tenant_id, is_active=True)
        settings = tenant.settings

        if not settings.correios_enabled:
            return {"status": "skipped", "reason": "disabled"}

        # get_correios_client já renova o token se necessário
        clients = get_correios_client(settings)

        if clients:
            logger.info("Token Correios renovado para tenant %s", tenant.slug)
            return {"status": "renewed"}
        else:
            return {"status": "failed"}

    except Tenant.DoesNotExist:
        return {"status": "error", "reason": "tenant_not_found"}
    except Exception as e:
        logger.exception("Erro ao renovar token Correios: %s", e)
        return {"status": "error", "reason": str(e)}
