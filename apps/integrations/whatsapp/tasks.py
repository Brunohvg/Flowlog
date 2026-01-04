"""
Tasks Celery para envio de mensagens via WhatsApp.
"""

import logging

from celery import shared_task

from apps.integrations.whatsapp.services import WhatsAppNotificationService

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 10},
    retry_backoff=True,
    retry_jitter=True,
)
def send_order_created_whatsapp(self, order_id):
    """
    Envia mensagem de pedido criado via WhatsApp.
    Executa de forma assíncrona com retry automático.
    """
    Order = apps.get_model("orders", "Order")

    try:
        order = Order.objects.select_related("customer", "tenant").get(id=order_id)
    except Order.DoesNotExist:
        logger.warning(
            "WhatsApp task abortada | order_not_found | order_id=%s",
            order_id,
        )
        return

    logger.info(
        "WhatsApp task start | event=order_created | order=%s",
        order.id,
    )

    service = WhatsAppNotificationService(order.tenant)
    service.send_order_created(order)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 10},
    retry_backoff=True,
    retry_jitter=True,
)
def send_order_shipped_whatsapp(self, order_id):
    from apps.orders.models import Order

    try:
        order = Order.objects.select_related("customer", "tenant").get(id=order_id)
    except Order.DoesNotExist:
        logger.warning(
            "WhatsApp task abortada | event=order_shipped | order_not_found | order_id=%s",
            order_id,
        )
        return

    logger.info(
        "WhatsApp task start | event=order_shipped | order=%s",
        order.id,
    )

    WhatsAppNotificationService(order.tenant).send_order_shipped(order)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 10},
    retry_backoff=True,
    retry_jitter=True,
)
def send_order_delivered_whatsapp(self, order_id):
    from apps.orders.models import Order

    try:
        order = Order.objects.select_related("customer", "tenant").get(id=order_id)
    except Order.DoesNotExist:
        logger.warning(
            "WhatsApp task abortada | event=order_delivered | order_not_found | order_id=%s",
            order_id,
        )
        return

    logger.info(
        "WhatsApp task start | event=order_delivered | order=%s",
        order.id,
    )

    WhatsAppNotificationService(order.tenant).send_order_delivered(order)
