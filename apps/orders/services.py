"""
Services - Flowlog.
Race Condition: transaction.on_commit() para WhatsApp.
Concorrência: select_for_update() para Lost Update.
"""

import logging
from datetime import timedelta
from functools import partial

from django.db import transaction as db_transaction
from django.utils import timezone

from apps.integrations.whatsapp.tasks import (
    send_order_created_whatsapp,
    send_order_confirmed_whatsapp,
    send_payment_received_whatsapp,
    send_payment_refunded_whatsapp,
    send_order_shipped_whatsapp,
    send_order_delivered_whatsapp,
    send_delivery_failed_whatsapp,
    send_order_ready_for_pickup_whatsapp,
    send_order_picked_up_whatsapp,
    send_order_cancelled_whatsapp,
    send_order_returned_whatsapp,
)
from apps.orders.models import (
    Customer, DeliveryStatus, DeliveryType, Order,
    OrderActivity, OrderStatus, PaymentStatus,
)

logger = logging.getLogger(__name__)
PICKUP_EXPIRY_HOURS = 48


def validate_cpf(cpf: str) -> bool:
    cpf = ''.join(filter(str.isdigit, cpf))
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    soma = sum(int(cpf[i]) * (10 - i) for i in range(9))
    d1 = 0 if soma % 11 < 2 else 11 - soma % 11
    if int(cpf[9]) != d1:
        return False
    soma = sum(int(cpf[i]) * (11 - i) for i in range(10))
    d2 = 0 if soma % 11 < 2 else 11 - soma % 11
    return int(cpf[10]) == d2


def normalize_cpf(cpf: str) -> str:
    return ''.join(filter(str.isdigit, cpf))


def _send_whatsapp(task, order_id: str):
    from django.conf import settings
    if getattr(settings, 'DEBUG', False):
        return
    if not getattr(settings, 'CELERY_BROKER_URL', ''):
        return
    try:
        task.apply_async(args=[order_id], expires=300)
    except Exception:
        pass


def _schedule_whatsapp(task, order_id: str):
    db_transaction.on_commit(partial(_send_whatsapp, task, order_id))


class OrderService:

    @db_transaction.atomic
    def create_order(self, *, tenant, seller, data):
        if seller.tenant_id != tenant.id:
            raise ValueError("Usuário não pertence ao tenant.")

        phone = data["customer_phone"]
        phone_normalized = "".join(filter(str.isdigit, phone))
        
        cpf = data.get("customer_cpf", "")
        if cpf:
            cpf = normalize_cpf(cpf)
            if cpf and not validate_cpf(cpf):
                raise ValueError("CPF inválido.")

        customer, created = Customer.objects.get_or_create(
            tenant=tenant,
            phone_normalized=phone_normalized,
            defaults={"name": data["customer_name"], "phone": phone, "cpf": cpf},
        )
        
        if not created:
            if data["customer_name"] and data["customer_name"] != customer.name:
                customer.name = data["customer_name"]
                customer.save(update_fields=["name"])
            if cpf and not customer.cpf:
                customer.cpf = cpf
                customer.save(update_fields=["cpf"])
        
        if customer.is_blocked:
            raise ValueError("Cliente bloqueado.")

        delivery_type = data.get("delivery_type", DeliveryType.MOTOBOY)
        delivery_address = "" if delivery_type == DeliveryType.PICKUP else data.get("delivery_address", "")
        
        if delivery_type != DeliveryType.PICKUP and not delivery_address.strip():
            raise ValueError("Endereço obrigatório.")

        order = Order.objects.create(
            tenant=tenant, customer=customer, seller=seller,
            total_value=data["total_value"], delivery_type=delivery_type,
            delivery_status=DeliveryStatus.PENDING, delivery_address=delivery_address,
            notes=data.get("notes", ""), is_priority=data.get("is_priority", False),
        )

        OrderActivity.log(
            order=order, activity_type=OrderActivity.ActivityType.CREATED,
            description=f"Criado por {seller.get_full_name() or seller.email}",
            user=seller, delivery_type=delivery_type, total_value=str(order.total_value),
        )

        _schedule_whatsapp(send_order_created_whatsapp, str(order.id))
        return order

    @db_transaction.atomic
    def duplicate_order(self, *, order: Order, actor):
        if order.tenant_id != actor.tenant_id:
            raise ValueError("Usuário não pertence ao tenant.")

        new_order = Order.objects.create(
            tenant=order.tenant, customer=order.customer, seller=actor,
            total_value=order.total_value, delivery_type=order.delivery_type,
            delivery_status=DeliveryStatus.PENDING, delivery_address=order.delivery_address,
            notes=f"Cópia de {order.code}",
        )

        OrderActivity.log(
            order=new_order, activity_type=OrderActivity.ActivityType.CREATED,
            description=f"Duplicado de {order.code}", user=actor,
        )

        _schedule_whatsapp(send_order_created_whatsapp, str(new_order.id))
        return new_order


class OrderStatusService:

    @db_transaction.atomic
    def mark_as_paid(self, *, order: Order, actor):
        if order.tenant_id != actor.tenant_id:
            raise ValueError("Usuário não pertence ao tenant.")
        order = Order.objects.select_for_update().get(id=order.id)
        if order.payment_status == PaymentStatus.PAID:
            return order
        order.payment_status = PaymentStatus.PAID
        if order.order_status == OrderStatus.PENDING:
            order.order_status = OrderStatus.CONFIRMED
        order.save(update_fields=["payment_status", "order_status", "updated_at"])
        OrderActivity.log(order=order, activity_type=OrderActivity.ActivityType.PAYMENT_RECEIVED,
                          description="Pagamento confirmado", user=actor)
        _schedule_whatsapp(send_payment_received_whatsapp, str(order.id))
        return order

    @db_transaction.atomic
    def mark_as_shipped(self, *, order: Order, actor, tracking_code: str = None):
        if order.tenant_id != actor.tenant_id:
            raise ValueError("Usuário não pertence ao tenant.")
        if not DeliveryType.is_delivery(order.delivery_type):
            raise ValueError("Pedido de retirada não pode ser enviado.")
        order = Order.objects.select_for_update().get(id=order.id)
        if order.order_status in [OrderStatus.CANCELLED, OrderStatus.RETURNED]:
            raise ValueError("Pedido cancelado/devolvido.")
        if order.delivery_status == DeliveryStatus.SHIPPED:
            return order
        if order.delivery_status not in [DeliveryStatus.PENDING, DeliveryStatus.FAILED_ATTEMPT]:
            raise ValueError("Status inválido para envio.")
        if DeliveryType.requires_tracking(order.delivery_type):
            if not tracking_code or not tracking_code.strip():
                raise ValueError(f"Rastreio obrigatório para {order.get_delivery_type_display()}.")
            order.tracking_code = tracking_code.strip().upper()
        elif tracking_code:
            order.tracking_code = tracking_code.strip().upper()
        order.delivery_status = DeliveryStatus.SHIPPED
        order.shipped_at = timezone.now()
        if order.order_status == OrderStatus.PENDING:
            order.order_status = OrderStatus.CONFIRMED
        order.save(update_fields=["delivery_status", "shipped_at", "tracking_code", "order_status", "updated_at"])
        OrderActivity.log(order=order, activity_type=OrderActivity.ActivityType.SHIPPED,
                          description=f"Enviado{f' - {order.tracking_code}' if order.tracking_code else ''}", user=actor)
        _schedule_whatsapp(send_order_shipped_whatsapp, str(order.id))
        return order

    @db_transaction.atomic
    def mark_as_delivered(self, *, order: Order, actor):
        if order.tenant_id != actor.tenant_id:
            raise ValueError("Usuário não pertence ao tenant.")
        if not DeliveryType.is_delivery(order.delivery_type):
            raise ValueError("Use retirada para pickup.")
        order = Order.objects.select_for_update().get(id=order.id)
        if order.delivery_status == DeliveryStatus.DELIVERED:
            return order
        if order.delivery_status not in [DeliveryStatus.SHIPPED, DeliveryStatus.FAILED_ATTEMPT]:
            raise ValueError("Precisa estar enviado.")
        order.delivery_status = DeliveryStatus.DELIVERED
        order.delivered_at = timezone.now()
        order.order_status = OrderStatus.COMPLETED
        order.save(update_fields=["delivery_status", "delivered_at", "order_status", "updated_at"])
        OrderActivity.log(order=order, activity_type=OrderActivity.ActivityType.DELIVERED,
                          description="Entregue", user=actor)
        _schedule_whatsapp(send_order_delivered_whatsapp, str(order.id))
        return order

    @db_transaction.atomic
    def mark_failed_attempt(self, *, order: Order, actor, reason: str = ""):
        if order.tenant_id != actor.tenant_id:
            raise ValueError("Usuário não pertence ao tenant.")
        order = Order.objects.select_for_update().get(id=order.id)
        if order.delivery_status != DeliveryStatus.SHIPPED:
            raise ValueError("Precisa estar enviado.")
        order.delivery_status = DeliveryStatus.FAILED_ATTEMPT
        order.delivery_attempts += 1
        order.save(update_fields=["delivery_status", "delivery_attempts", "updated_at"])
        OrderActivity.log(order=order, activity_type=OrderActivity.ActivityType.FAILED_ATTEMPT,
                          description=f"Tentativa {order.delivery_attempts} falha. {reason}".strip(), user=actor)
        _schedule_whatsapp(send_delivery_failed_whatsapp, str(order.id))
        return order

    @db_transaction.atomic
    def mark_ready_for_pickup(self, *, order: Order, actor):
        if order.tenant_id != actor.tenant_id:
            raise ValueError("Usuário não pertence ao tenant.")
        if order.delivery_type != DeliveryType.PICKUP:
            raise ValueError("Apenas retirada.")
        order = Order.objects.select_for_update().get(id=order.id)
        if order.order_status in [OrderStatus.CANCELLED, OrderStatus.RETURNED]:
            raise ValueError("Cancelado/devolvido.")
        if order.delivery_status == DeliveryStatus.READY_FOR_PICKUP:
            return order
        if order.delivery_status != DeliveryStatus.PENDING:
            raise ValueError("Não está pendente.")
        order.pickup_code = order.generate_pickup_code()
        order.delivery_status = DeliveryStatus.READY_FOR_PICKUP
        order.shipped_at = timezone.now()
        order.expires_at = timezone.now() + timedelta(hours=PICKUP_EXPIRY_HOURS)
        if order.order_status == OrderStatus.PENDING:
            order.order_status = OrderStatus.CONFIRMED
        order.save(update_fields=["delivery_status", "shipped_at", "expires_at", "order_status", "pickup_code", "updated_at"])
        OrderActivity.log(order=order, activity_type=OrderActivity.ActivityType.READY_PICKUP,
                          description=f"Pronto. Código: {order.pickup_code}", user=actor)
        _schedule_whatsapp(send_order_ready_for_pickup_whatsapp, str(order.id))
        return order

    @db_transaction.atomic
    def mark_as_picked_up(self, *, order: Order, actor):
        if order.tenant_id != actor.tenant_id:
            raise ValueError("Usuário não pertence ao tenant.")
        if order.delivery_type != DeliveryType.PICKUP:
            raise ValueError("Apenas retirada.")
        order = Order.objects.select_for_update().get(id=order.id)
        if order.delivery_status == DeliveryStatus.PICKED_UP:
            return order
        if order.delivery_status != DeliveryStatus.READY_FOR_PICKUP:
            raise ValueError("Precisa estar pronto.")
        order.delivery_status = DeliveryStatus.PICKED_UP
        order.delivered_at = timezone.now()
        order.order_status = OrderStatus.COMPLETED
        order.expires_at = None
        order.save(update_fields=["delivery_status", "delivered_at", "order_status", "expires_at", "updated_at"])
        OrderActivity.log(order=order, activity_type=OrderActivity.ActivityType.PICKED_UP,
                          description="Retirado", user=actor)
        _schedule_whatsapp(send_order_picked_up_whatsapp, str(order.id))
        return order

    @db_transaction.atomic
    def cancel_order(self, *, order: Order, actor, reason: str = ""):
        if order.tenant_id != actor.tenant_id:
            raise ValueError("Usuário não pertence ao tenant.")
        order = Order.objects.select_for_update().get(id=order.id)
        if order.order_status == OrderStatus.CANCELLED:
            return order
        if order.order_status == OrderStatus.RETURNED:
            raise ValueError("Devolvido não pode cancelar.")
        order.order_status = OrderStatus.CANCELLED
        order.cancel_reason = reason
        order.cancelled_at = timezone.now()
        order.save(update_fields=["order_status", "cancel_reason", "cancelled_at", "updated_at"])
        OrderActivity.log(order=order, activity_type=OrderActivity.ActivityType.CANCELLED,
                          description=f"Cancelado. {reason}".strip(), user=actor)
        _schedule_whatsapp(send_order_cancelled_whatsapp, str(order.id))
        return order

    @db_transaction.atomic
    def return_order(self, *, order: Order, actor, reason: str = "", refund: bool = False):
        if order.tenant_id != actor.tenant_id:
            raise ValueError("Usuário não pertence ao tenant.")
        order = Order.objects.select_for_update().get(id=order.id)
        if order.order_status != OrderStatus.COMPLETED:
            raise ValueError("Apenas concluídos.")
        if order.delivery_status not in [DeliveryStatus.DELIVERED, DeliveryStatus.PICKED_UP]:
            raise ValueError("Precisa ter sido entregue/retirado.")
        order.order_status = OrderStatus.RETURNED
        order.return_reason = reason
        order.returned_at = timezone.now()
        if refund and order.payment_status == PaymentStatus.PAID:
            order.payment_status = PaymentStatus.REFUNDED
        order.save(update_fields=["order_status", "return_reason", "returned_at", "payment_status", "updated_at"])
        OrderActivity.log(order=order, activity_type=OrderActivity.ActivityType.RETURNED,
                          description=f"Devolvido. {reason}".strip(), user=actor)
        if refund:
            OrderActivity.log(order=order, activity_type=OrderActivity.ActivityType.REFUNDED,
                              description="Reembolsado", user=actor)
            _schedule_whatsapp(send_payment_refunded_whatsapp, str(order.id))
        _schedule_whatsapp(send_order_returned_whatsapp, str(order.id))
        return order

    @db_transaction.atomic
    def change_delivery_type(self, *, order: Order, actor, new_type: str, address: str = ""):
        if order.tenant_id != actor.tenant_id:
            raise ValueError("Usuário não pertence ao tenant.")
        order = Order.objects.select_for_update().get(id=order.id)
        if not order.can_change_delivery_type:
            raise ValueError("Não pode alterar agora.")
        old_type = order.delivery_type
        if new_type == DeliveryType.PICKUP:
            address = ""
        elif DeliveryType.requires_address(new_type) and not address.strip():
            raise ValueError("Endereço obrigatório.")
        if order.delivery_status == DeliveryStatus.READY_FOR_PICKUP and new_type != DeliveryType.PICKUP:
            order.delivery_status = DeliveryStatus.PENDING
            order.expires_at = None
        order.delivery_type = new_type
        order.delivery_address = address
        order.tracking_code = ""
        order.save(update_fields=["delivery_type", "delivery_address", "tracking_code", "delivery_status", "expires_at", "updated_at"])
        OrderActivity.log(order=order, activity_type=OrderActivity.ActivityType.DELIVERY_TYPE_CHANGED,
                          description=f"{dict(DeliveryType.choices)[old_type]} -> {dict(DeliveryType.choices)[new_type]}", user=actor)
        return order

    @db_transaction.atomic
    def expire_pickup_order(self, *, order: Order):
        order = Order.objects.select_for_update().get(id=order.id)
        if order.delivery_type != DeliveryType.PICKUP:
            return order
        if order.delivery_status != DeliveryStatus.READY_FOR_PICKUP:
            return order
        if not order.expires_at or timezone.now() < order.expires_at:
            return order
        order.delivery_status = DeliveryStatus.EXPIRED
        order.order_status = OrderStatus.CANCELLED
        order.cancel_reason = "Retirada não realizada no prazo"
        order.cancelled_at = timezone.now()
        order.save(update_fields=["delivery_status", "order_status", "cancel_reason", "cancelled_at", "updated_at"])
        OrderActivity.log(order=order, activity_type=OrderActivity.ActivityType.EXPIRED,
                          description=f"Expirado - {PICKUP_EXPIRY_HOURS}h", user=None)
        return order

    def resend_notification(self, *, order: Order, notification_type: str):
        if order.order_status in [OrderStatus.CANCELLED, OrderStatus.RETURNED]:
            if notification_type not in ["cancelled", "returned"]:
                raise ValueError("Não pode enviar para cancelado/devolvido.")
        tasks = {
            "created": send_order_created_whatsapp, "confirmed": send_order_confirmed_whatsapp,
            "payment": send_payment_received_whatsapp, "shipped": send_order_shipped_whatsapp,
            "delivered": send_order_delivered_whatsapp, "ready_pickup": send_order_ready_for_pickup_whatsapp,
            "picked_up": send_order_picked_up_whatsapp, "cancelled": send_order_cancelled_whatsapp,
            "returned": send_order_returned_whatsapp,
        }
        task = tasks.get(notification_type)
        if not task:
            raise ValueError(f"Tipo inválido: {notification_type}")
        _send_whatsapp(task, str(order.id))
        OrderActivity.log(order=order, activity_type=OrderActivity.ActivityType.NOTIFICATION_SENT,
                          description=f"Reenviado: {notification_type}", user=None)

    @db_transaction.atomic
    def delete_order(self, *, order: Order, actor):
        """Deleta pedido permanentemente. Só permite se PENDING ou CANCELLED."""
        if order.tenant_id != actor.tenant_id:
            raise ValueError("Usuário não pertence ao tenant.")
        if order.order_status not in [OrderStatus.PENDING, OrderStatus.CANCELLED]:
            raise ValueError("Só pode deletar pedidos pendentes ou cancelados.")
        if order.payment_status == PaymentStatus.PAID:
            raise ValueError("Não pode deletar pedido pago.")
        order_code = order.code
        order.delete()
        return order_code
