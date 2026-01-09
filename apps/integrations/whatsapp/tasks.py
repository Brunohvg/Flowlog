"""
Tasks Celery para WhatsApp.
OrderNotFoundError permite retry (resolve Race Condition).
"""

import logging
from functools import partial

from celery import shared_task
from django.apps import apps
from django.db import transaction

from apps.integrations.whatsapp.services import WhatsAppNotificationService

logger = logging.getLogger(__name__)


class OrderNotFoundError(Exception):
    pass


def _get_order(order_id: str):
    Order = apps.get_model("orders", "Order")
    try:
        return Order.objects.select_related("customer", "tenant", "tenant__settings").get(id=order_id)
    except Order.DoesNotExist:
        raise OrderNotFoundError(f"Order {order_id} not found")


TASK_CONFIG = {
    "bind": True,
    "autoretry_for": (Exception, OrderNotFoundError),
    "retry_kwargs": {"max_retries": 5, "countdown": 5},
    "retry_backoff": True,
    "retry_backoff_max": 60,
    "retry_jitter": True,
    "acks_late": True,
    "reject_on_worker_lost": True,
}


def _process(self, order_id: str, method: str):
    order = _get_order(order_id)
    service = WhatsAppNotificationService(order.tenant)
    func = getattr(service, method, None)
    if func:
        return func(order)
    return {"success": False}


@shared_task(**TASK_CONFIG)
def send_order_created_whatsapp(self, order_id):
    return _process(self, order_id, "send_order_created")


@shared_task(**TASK_CONFIG)
def send_order_confirmed_whatsapp(self, order_id):
    return _process(self, order_id, "send_order_confirmed")


@shared_task(**TASK_CONFIG)
def send_payment_received_whatsapp(self, order_id):
    return _process(self, order_id, "send_payment_received")


@shared_task(**TASK_CONFIG)
def send_payment_refunded_whatsapp(self, order_id):
    return _process(self, order_id, "send_payment_refunded")


@shared_task(**TASK_CONFIG)
def send_order_shipped_whatsapp(self, order_id):
    return _process(self, order_id, "send_order_shipped")


@shared_task(**TASK_CONFIG)
def send_order_delivered_whatsapp(self, order_id):
    return _process(self, order_id, "send_order_delivered")


@shared_task(**TASK_CONFIG)
def send_delivery_failed_whatsapp(self, order_id):
    return _process(self, order_id, "send_delivery_failed")


@shared_task(**TASK_CONFIG)
def send_order_ready_for_pickup_whatsapp(self, order_id):
    return _process(self, order_id, "send_order_ready_for_pickup")


@shared_task(**TASK_CONFIG)
def send_order_picked_up_whatsapp(self, order_id):
    return _process(self, order_id, "send_order_picked_up")


@shared_task(**TASK_CONFIG)
def send_order_expired_whatsapp(self, order_id):
    return _process(self, order_id, "send_order_expired")


@shared_task(**TASK_CONFIG)
def send_order_cancelled_whatsapp(self, order_id):
    return _process(self, order_id, "send_order_cancelled")


@shared_task(**TASK_CONFIG)
def send_order_returned_whatsapp(self, order_id):
    return _process(self, order_id, "send_order_returned")


@shared_task(bind=True)
def expire_pending_pickups(self):
    from apps.orders.models import Order, DeliveryStatus, DeliveryType
    from apps.orders.services import OrderStatusService
    from django.utils import timezone
    
    orders = Order.objects.filter(
        delivery_type=DeliveryType.PICKUP,
        delivery_status=DeliveryStatus.READY_FOR_PICKUP,
        expires_at__lt=timezone.now(),
    )
    
    service = OrderStatusService()
    count = 0
    
    for order in orders:
        try:
            service.expire_pickup_order(order=order)
            transaction.on_commit(partial(send_order_expired_whatsapp.delay, str(order.id)))
            count += 1
        except Exception:
            pass
    
    return {"expired": count}
