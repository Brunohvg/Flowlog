"""
Tasks Celery para envio de mensagens via WhatsApp.
Cobre TODOS os status de pedido, pagamento e entrega.
"""

import logging

from celery import shared_task
from django.apps import apps

from apps.integrations.whatsapp.services import WhatsAppNotificationService

logger = logging.getLogger(__name__)


def _get_order(order_id, event_name):
    """Helper para buscar pedido com tratamento de erro."""
    Order = apps.get_model("orders", "Order")
    try:
        return Order.objects.select_related("customer", "tenant", "tenant__settings").get(id=order_id)
    except Order.DoesNotExist:
        logger.warning("WhatsApp task abortada | event=%s | order_not_found | order_id=%s", event_name, order_id)
        return None


# ==================== PEDIDO ====================

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 10},
    retry_backoff=True,
    retry_jitter=True,
)
def send_order_created_whatsapp(self, order_id):
    """Envia mensagem de pedido criado."""
    order = _get_order(order_id, "order_created")
    if not order:
        return
    
    logger.info("WhatsApp | event=order_created | order=%s", order.code)
    WhatsAppNotificationService(order.tenant).send_order_created(order)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 10},
    retry_backoff=True,
    retry_jitter=True,
)
def send_order_confirmed_whatsapp(self, order_id):
    """Envia mensagem de pedido confirmado."""
    order = _get_order(order_id, "order_confirmed")
    if not order:
        return
    
    logger.info("WhatsApp | event=order_confirmed | order=%s", order.code)
    WhatsAppNotificationService(order.tenant).send_order_confirmed(order)


# ==================== PAGAMENTO ====================

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 10},
    retry_backoff=True,
    retry_jitter=True,
)
def send_payment_received_whatsapp(self, order_id):
    """Envia mensagem de pagamento recebido."""
    order = _get_order(order_id, "payment_received")
    if not order:
        return
    
    logger.info("WhatsApp | event=payment_received | order=%s", order.code)
    WhatsAppNotificationService(order.tenant).send_payment_received(order)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 10},
    retry_backoff=True,
    retry_jitter=True,
)
def send_payment_refunded_whatsapp(self, order_id):
    """Envia mensagem de estorno de pagamento."""
    order = _get_order(order_id, "payment_refunded")
    if not order:
        return
    
    logger.info("WhatsApp | event=payment_refunded | order=%s", order.code)
    WhatsAppNotificationService(order.tenant).send_payment_refunded(order)


# ==================== ENTREGA ====================

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 10},
    retry_backoff=True,
    retry_jitter=True,
)
def send_order_shipped_whatsapp(self, order_id):
    """Envia mensagem de pedido enviado."""
    order = _get_order(order_id, "order_shipped")
    if not order:
        return
    
    logger.info("WhatsApp | event=order_shipped | order=%s | tracking=%s", order.code, order.tracking_code or "N/A")
    WhatsAppNotificationService(order.tenant).send_order_shipped(order)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 10},
    retry_backoff=True,
    retry_jitter=True,
)
def send_order_delivered_whatsapp(self, order_id):
    """Envia mensagem de pedido entregue."""
    order = _get_order(order_id, "order_delivered")
    if not order:
        return
    
    logger.info("WhatsApp | event=order_delivered | order=%s", order.code)
    WhatsAppNotificationService(order.tenant).send_order_delivered(order)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 10},
    retry_backoff=True,
    retry_jitter=True,
)
def send_delivery_failed_whatsapp(self, order_id):
    """Envia mensagem de tentativa de entrega falha."""
    order = _get_order(order_id, "delivery_failed")
    if not order:
        return
    
    logger.info("WhatsApp | event=delivery_failed | order=%s | attempt=%s", order.code, order.delivery_attempts)
    WhatsAppNotificationService(order.tenant).send_delivery_failed(order)


# ==================== RETIRADA ====================

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 10},
    retry_backoff=True,
    retry_jitter=True,
)
def send_order_ready_for_pickup_whatsapp(self, order_id):
    """Envia mensagem de pedido pronto para retirada."""
    order = _get_order(order_id, "ready_for_pickup")
    if not order:
        return
    
    logger.info("WhatsApp | event=ready_for_pickup | order=%s", order.code)
    WhatsAppNotificationService(order.tenant).send_order_ready_for_pickup(order)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 10},
    retry_backoff=True,
    retry_jitter=True,
)
def send_order_picked_up_whatsapp(self, order_id):
    """Envia mensagem de pedido retirado."""
    order = _get_order(order_id, "picked_up")
    if not order:
        return
    
    logger.info("WhatsApp | event=picked_up | order=%s", order.code)
    WhatsAppNotificationService(order.tenant).send_order_picked_up(order)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 10},
    retry_backoff=True,
    retry_jitter=True,
)
def send_order_expired_whatsapp(self, order_id):
    """Envia mensagem de pedido expirado (retirada não realizada)."""
    order = _get_order(order_id, "expired")
    if not order:
        return
    
    logger.info("WhatsApp | event=expired | order=%s", order.code)
    WhatsAppNotificationService(order.tenant).send_order_expired(order)


# ==================== CANCELAMENTO ====================

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 10},
    retry_backoff=True,
    retry_jitter=True,
)
def send_order_cancelled_whatsapp(self, order_id):
    """Envia mensagem de pedido cancelado."""
    order = _get_order(order_id, "cancelled")
    if not order:
        return
    
    logger.info("WhatsApp | event=cancelled | order=%s", order.code)
    WhatsAppNotificationService(order.tenant).send_order_cancelled(order)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 10},
    retry_backoff=True,
    retry_jitter=True,
)
def send_order_returned_whatsapp(self, order_id):
    """Envia mensagem de pedido devolvido."""
    order = _get_order(order_id, "returned")
    if not order:
        return
    
    logger.info("WhatsApp | event=returned | order=%s", order.code)
    WhatsAppNotificationService(order.tenant).send_order_returned(order)


# ==================== TASK PERIÓDICA ====================

@shared_task
def expire_pending_pickups():
    """
    Task periódica para expirar pedidos de retirada não realizados.
    Deve ser executada a cada hora via Celery Beat.
    """
    from apps.orders.models import Order, DeliveryStatus, DeliveryType
    from apps.orders.services import OrderStatusService
    from django.utils import timezone
    
    # Busca pedidos de retirada que expiraram
    expired_orders = Order.objects.filter(
        delivery_type=DeliveryType.PICKUP,
        delivery_status=DeliveryStatus.READY_FOR_PICKUP,
        expires_at__lt=timezone.now(),
    )
    
    service = OrderStatusService()
    count = 0
    
    for order in expired_orders:
        try:
            service.expire_pickup_order(order=order)
            # Notifica cliente via WhatsApp
            send_order_expired_whatsapp.delay(str(order.id))
            count += 1
        except Exception as e:
            logger.error("Erro ao expirar pedido %s: %s", order.code, e)
    
    logger.info("Task expire_pending_pickups | expired=%d orders", count)
    return count
