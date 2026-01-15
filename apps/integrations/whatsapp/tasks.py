"""
Tasks Celery para WhatsApp - Flowlog.
Gerencia o envio assíncrono de notificações com alta resiliência.

Arquitetura:
1. Snapshot: Dados são 'congelados' no momento do evento para evitar Race Conditions.
2. Serialização: Uso de DjangoJSONEncoder para suportar Decimal e Datas.
3. Filas: Processamento isolado na fila 'whatsapp'.
"""

import json
import logging
import time
import requests

from celery import shared_task
from django.apps import apps
from django.core.serializers.json import (
    DjangoJSONEncoder,  # Essencial para serializar Decimal/Date
)
from django.db import transaction

from apps.integrations.whatsapp.services import WhatsAppNotificationService

logger = logging.getLogger(__name__)

# Configuração robusta para Tasks de Mensageria
TASK_CONFIG = {
    "bind": True,
    "autoretry_for": (
        requests.exceptions.RequestException,
    ),  # Retenta apenas em erros de rede/timeout
    "retry_kwargs": {"max_retries": 5, "countdown": 10},  # Backoff: 10s, 20s...
    "retry_backoff": True,
    "retry_backoff_max": 120,
    "retry_jitter": True,
    "acks_late": True,  # Garante que a task só é removida da fila se sucesso
    "reject_on_worker_lost": True,
    "queue": "whatsapp",  # Fila dedicada
}


class OrderNotFoundError(Exception):
    pass


def _get_order(order_id: str):
    """
    Helper para buscar pedido no banco.
    Usado apenas em tasks legadas ou específicas (como PaymentLink).
    """
    Order = apps.get_model("orders", "Order")
    try:
        return Order.objects.select_related(
            "customer", "tenant", "tenant__settings"
        ).get(id=order_id)
    except Order.DoesNotExist:
        raise OrderNotFoundError(f"Order {order_id} not found")


def create_order_snapshot(order) -> dict:
    """
    Cria um dicionário (snapshot) com os dados do pedido.

    Objetivo: Congelar o estado do pedido no momento do evento.
    Isso evita inconsistências se o pedido for alterado enquanto a task aguarda na fila.
    """
    return {
        "order_id": str(order.id),
        "code": order.code,
        # Mantemos str() para total_value por segurança dupla,
        # embora o DjangoJSONEncoder lidaria com Decimal se necessário.
        "total_value": str(order.total_value),
        "customer_name": order.customer.name if order.customer else "",
        "customer_phone": order.customer.phone_normalized if order.customer else "",
        "tenant_id": str(order.tenant_id),
        "tracking_code": order.tracking_code or "",
        "pickup_code": order.pickup_code or "",
        "delivery_attempts": getattr(order, "delivery_attempts", 0),
        "cancel_reason": getattr(order, "cancel_reason", "") or "",
        "return_reason": getattr(order, "return_reason", "") or "",
    }


def _process_with_snapshot(snapshot: dict, method: str):
    """
    Núcleo de processamento via Snapshot.
    Recebe dados puros (dict), instancia o serviço e dispara o envio.
    """
    from apps.tenants.models import Tenant

    # 1. Busca configurações do Tenant
    try:
        tenant = Tenant.objects.select_related("settings").get(id=snapshot["tenant_id"])
    except Tenant.DoesNotExist:
        logger.error(
            "[WhatsApp] Tenant ID %s não encontrado no snapshot",
            snapshot.get("tenant_id"),
        )
        return {"success": False, "error": "Tenant not found"}
    except Exception as e:
        logger.error("[WhatsApp] Erro ao buscar tenant: %s", e)
        raise e  # Levanta erro para o Celery tentar novamente

    # 2. Executa envio
    try:
        service = WhatsAppNotificationService(tenant)
        func = getattr(service, method, None)

        if not func:
            logger.error("[WhatsApp] Método '%s' não existe no serviço", method)
            return {"success": False, "error": f"Method {method} not found"}

        # O serviço sabe lidar com dict (snapshot) graças ao _extract_data implementado
        result = func(snapshot)

        # Pequeno delay para aliviar rate-limits em disparos em massa
        time.sleep(0.1)
        return result

    except Exception as e:
        logger.exception(
            "[WhatsApp] Erro crítico ao processar snapshot method=%s", method
        )
        raise e


def _process_legacy(self, order_id: str, method: str):
    """
    Processamento legado (baseado em ID).
    Mantido para compatibilidade com tasks antigas que ainda possam estar na fila.
    """
    try:
        order = _get_order(order_id)
        service = WhatsAppNotificationService(order.tenant)
        func = getattr(service, method, None)

        if func:
            return func(order)

        return {"success": False, "error": f"Method {method} not found"}

    except OrderNotFoundError:
        logger.warning("[WhatsApp] Order %s não encontrado (Legacy)", order_id)
        return {"success": False, "error": "Order not found"}
    except Exception as e:
        logger.exception("[WhatsApp] Falha legacy order=%s method=%s", order_id, method)
        raise e


# ==============================================================================
# TASKS PRINCIPAIS (Snapshot - Recomendadas)
# ==============================================================================


@shared_task(**TASK_CONFIG)
def send_whatsapp_notification(self, snapshot_json: str, method: str):
    """
    Task Única e Principal.
    Recebe JSON serializado, decodifica e processa.
    """
    try:
        snapshot = json.loads(snapshot_json)
        return _process_with_snapshot(snapshot, method)
    except json.JSONDecodeError as e:
        logger.error("[WhatsApp] JSON inválido recebido: %s", e)
        return {"success": False, "error": "Invalid JSON"}
    except Exception as e:
        logger.exception("[WhatsApp] Falha na task send_whatsapp_notification")
        raise e


# ==============================================================================
# TASKS LEGADAS (Compatibilidade)
# ==============================================================================


@shared_task(**TASK_CONFIG)
def send_order_created_whatsapp(self, order_id):
    return _process_legacy(self, order_id, "send_order_created")


@shared_task(**TASK_CONFIG)
def send_order_confirmed_whatsapp(self, order_id):
    return _process_legacy(self, order_id, "send_order_confirmed")


@shared_task(**TASK_CONFIG)
def send_payment_received_whatsapp(self, order_id):
    return _process_legacy(self, order_id, "send_payment_received")


@shared_task(**TASK_CONFIG)
def send_payment_failed_whatsapp(self, order_id):
    return _process_legacy(self, order_id, "send_payment_failed")


@shared_task(**TASK_CONFIG)
def send_payment_refunded_whatsapp(self, order_id):
    return _process_legacy(self, order_id, "send_payment_refunded")


@shared_task(**TASK_CONFIG)
def send_order_shipped_whatsapp(self, order_id):
    return _process_legacy(self, order_id, "send_order_shipped")


@shared_task(**TASK_CONFIG)
def send_order_delivered_whatsapp(self, order_id):
    return _process_legacy(self, order_id, "send_order_delivered")


@shared_task(**TASK_CONFIG)
def send_delivery_failed_whatsapp(self, order_id):
    return _process_legacy(self, order_id, "send_delivery_failed")


@shared_task(**TASK_CONFIG)
def send_order_ready_for_pickup_whatsapp(self, order_id):
    return _process_legacy(self, order_id, "send_order_ready_for_pickup")


@shared_task(**TASK_CONFIG)
def send_order_picked_up_whatsapp(self, order_id):
    return _process_legacy(self, order_id, "send_order_picked_up")


@shared_task(**TASK_CONFIG)
def send_order_expired_whatsapp(self, order_id):
    return _process_legacy(self, order_id, "send_order_expired")


@shared_task(**TASK_CONFIG)
def send_order_cancelled_whatsapp(self, order_id):
    return _process_legacy(self, order_id, "send_order_cancelled")


@shared_task(**TASK_CONFIG)
def send_order_returned_whatsapp(self, order_id):
    return _process_legacy(self, order_id, "send_order_returned")


@shared_task(**TASK_CONFIG)
def send_payment_link_whatsapp(self, order_id, payment_link_id):
    """
    Envia link de pagamento (Task Específica que requer busca no banco).
    """
    from apps.payments.models import PaymentLink

    try:
        order = _get_order(order_id)
        payment_link = PaymentLink.objects.get(id=payment_link_id)

        service = WhatsAppNotificationService(order.tenant)
        return service.send_payment_link(order, payment_link)

    except (OrderNotFoundError, PaymentLink.DoesNotExist) as e:
        logger.warning("[WhatsApp] Recurso não encontrado (PaymentLink): %s", e)
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.exception("[WhatsApp] Erro ao enviar link de pagamento")
        raise e


# ==============================================================================
# JOBS AGENDADOS (Celery Beat)
# ==============================================================================


@shared_task(bind=True, queue="whatsapp")
def expire_pending_pickups(self):
    """
    Job periódico: Verifica e expira pedidos de retirada vencidos.
    Usa SNAPSHOT + DjangoJSONEncoder para consistência absoluta.
    """
    from django.utils import timezone

    from apps.orders.models import DeliveryStatus, DeliveryType, Order
    from apps.orders.services import OrderStatusService

    # Busca pedidos prontos para retirada que já venceram
    orders = Order.objects.select_related("customer", "tenant").filter(
        delivery_type=DeliveryType.PICKUP,
        delivery_status=DeliveryStatus.READY_FOR_PICKUP,
        expires_at__lt=timezone.now(),
    )

    service = OrderStatusService()
    count = 0
    errors = 0

    for order in orders:
        try:
            # 1. Cria snapshot (congela dados antes da expiração)
            snapshot = create_order_snapshot(order)

            # 2. Serializa com Encoder Seguro (evita erro com Decimal/Date)
            snapshot_json = json.dumps(snapshot, cls=DjangoJSONEncoder)

            # 3. Executa a expiração no banco (o service já dispara o WhatsApp)
            service.expire_pickup_order(order=order)
            count += 1

        except Exception:
            logger.exception(
                "[WhatsApp] Erro ao processar expiração automática order=%s", order.id
            )
            errors += 1

    return {"expired": count, "errors": errors}
