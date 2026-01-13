"""
Tasks Celery para WhatsApp.
Usa padrão SNAPSHOT para evitar race condition.
"""

import json
import logging
import time

from celery import shared_task
from django.apps import apps
from django.db import transaction

from apps.integrations.whatsapp.services import WhatsAppNotificationService

logger = logging.getLogger(__name__)


class OrderNotFoundError(Exception):
    pass


def _get_order(order_id: str):
    """Busca order do banco (usado apenas quando necessário)."""
    Order = apps.get_model("orders", "Order")
    try:
        return Order.objects.select_related(
            "customer", "tenant", "tenant__settings"
        ).get(id=order_id)
    except Order.DoesNotExist:
        raise OrderNotFoundError(f"Order {order_id} not found")


def create_order_snapshot(order) -> dict:
    """
    Cria snapshot dos dados do pedido para envio via Celery.
    Evita race condition - dados são "congelados" no momento do evento.
    """
    return {
        "order_id": str(order.id),
        "code": order.code,
        "total_value": str(order.total_value),
        "customer_name": order.customer.name if order.customer else "",
        "customer_phone": order.customer.phone_normalized if order.customer else "",
        "tenant_id": str(order.tenant_id),
        "tracking_code": order.tracking_code or "",
        "pickup_code": order.pickup_code or "",
        "delivery_attempts": order.delivery_attempts,
        "cancel_reason": order.cancel_reason or "",
        "return_reason": order.return_reason or "",
    }


TASK_CONFIG = {
    "bind": True,
    "autoretry_for": (Exception, OrderNotFoundError),
    "retry_kwargs": {"max_retries": 5, "countdown": 10},
    "retry_backoff": True,
    "retry_backoff_max": 120,
    "retry_jitter": True,
    "acks_late": True,
    "reject_on_worker_lost": True,
    # "rate_limit": "10/m",
}


def _process_with_snapshot(snapshot: dict, method: str):
    """
    Processa envio usando snapshot (dados congelados).

    RESILIÊNCIA: Captura todos os erros, nunca trava.
    """
    from apps.tenants.models import Tenant

    try:
        tenant = Tenant.objects.select_related("settings").get(id=snapshot["tenant_id"])
    except Tenant.DoesNotExist:
        logger.warning(
            "[WhatsApp] Tenant não encontrado: %s", snapshot.get("tenant_id")
        )
        return {"success": False, "error": "Tenant not found"}
    except Exception as e:
        logger.warning("[WhatsApp] Erro ao buscar tenant: %s", e)
        return {"success": False, "error": str(e)}

    try:
        service = WhatsAppNotificationService(tenant)
        func = getattr(service, method, None)
        if func:
            result = func(snapshot)
            time.sleep(0.5)
            return result
        return {"success": False, "error": f"Method {method} not found"}
    except Exception as e:
        logger.warning("[WhatsApp] Erro ao processar snapshot method=%s: %s", method, e)
        return {"success": False, "error": str(e)}


def _process_legacy(self, order_id: str, method: str):
    """
    Modo legado - lê do banco.

    RESILIÊNCIA: Captura todos os erros, nunca trava.
    """
    try:
        order = _get_order(order_id)
    except OrderNotFoundError:
        logger.warning("[WhatsApp] Order não encontrado: %s", order_id)
        return {"success": False, "error": "Order not found"}
    except Exception as e:
        logger.warning("[WhatsApp] Erro ao buscar order: %s", e)
        return {"success": False, "error": str(e)}

    try:
        service = WhatsAppNotificationService(order.tenant)
        func = getattr(service, method, None)
        if func:
            result = func(order)
            time.sleep(0.5)
            return result
        return {"success": False, "error": f"Method {method} not found"}
    except Exception as e:
        logger.warning("[WhatsApp] Erro ao processar legacy method=%s: %s", method, e)
        return {"success": False, "error": str(e)}


# ==============================================================================
# TASKS COM SNAPSHOT (novas)
# ==============================================================================


@shared_task(**TASK_CONFIG)
def send_whatsapp_notification(self, snapshot_json: str, method: str):
    """
    Task genérica que recebe snapshot JSON.
    Imune a race condition.
    """
    try:
        snapshot = json.loads(snapshot_json)
        return _process_with_snapshot(snapshot, method)
    except json.JSONDecodeError as e:
        logger.error("Snapshot JSON inválido: %s", str(e))
        return {"success": False, "error": "Invalid snapshot"}


# ==============================================================================
# TASKS LEGADAS (mantidas para compatibilidade com jobs em fila)
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
    Envia link de pagamento via WhatsApp.

    RESILIÊNCIA: Captura todos os erros.
    """
    from apps.payments.models import PaymentLink

    try:
        order = _get_order(order_id)
    except OrderNotFoundError:
        logger.warning(
            "[WhatsApp] Order não encontrado para payment_link: %s", order_id
        )
        return {"success": False, "error": "Order not found"}
    except Exception as e:
        logger.warning("[WhatsApp] Erro ao buscar order: %s", e)
        return {"success": False, "error": str(e)}

    try:
        payment_link = PaymentLink.objects.get(id=payment_link_id)
    except PaymentLink.DoesNotExist:
        logger.warning("[WhatsApp] PaymentLink não encontrado: %s", payment_link_id)
        return {"success": False, "error": "PaymentLink not found"}

    try:
        service = WhatsAppNotificationService(order.tenant)
        result = service.send_payment_link(order, payment_link)
        time.sleep(0.5)
        return result
    except Exception as e:
        logger.warning("[WhatsApp] Erro ao enviar payment_link: %s", e)
        return {"success": False, "error": str(e)}


@shared_task(bind=True)
def expire_pending_pickups(self):
    """
    Job agendado: Expira pedidos de retirada não retirados.

    Usa SNAPSHOT para garantir consistência dos dados.
    """
    from django.utils import timezone

    from apps.orders.models import DeliveryStatus, DeliveryType, Order
    from apps.orders.services import OrderStatusService

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
            # Cria snapshot ANTES de alterar o status
            snapshot = create_order_snapshot(order)
            snapshot_json = json.dumps(snapshot)

            # Expira o pedido
            service.expire_pickup_order(order=order)

            # Função segura para enviar notificação
            def _safe_send(sj=snapshot_json):
                try:
                    send_whatsapp_notification.apply_async(
                        args=[sj, "send_order_expired"],
                        expires=300,
                        ignore_result=True,
                    )
                except Exception as e:
                    logger.warning("[WhatsApp] Falha ao enviar expiração: %s", e)

            transaction.on_commit(_safe_send)
            count += 1
        except Exception as e:
            logger.warning("[WhatsApp] Erro ao expirar order=%s: %s", order.id, e)
            errors += 1

    return {"expired": count, "errors": errors}
