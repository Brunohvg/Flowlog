"""
Services - Flowlog.
Race Condition: Usa SNAPSHOT para WhatsApp (dados congelados no momento do evento).
Concorrência: select_for_update() para Lost Update.
"""

import json
import logging
import re
from datetime import timedelta
from decimal import Decimal, InvalidOperation

# ADICIONADO: Importação necessária para serializar Decimal/Date
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction as db_transaction
from django.utils import timezone

from apps.integrations.whatsapp.tasks import (  # Tasks legadas
    create_order_snapshot,
    send_whatsapp_notification,
)
from apps.orders.models import (
    Customer,
    DeliveryStatus,
    DeliveryType,
    Order,
    OrderActivity,
    OrderStatus,
    PaymentStatus,
)

logger = logging.getLogger(__name__)
PICKUP_EXPIRY_HOURS = 48


# ==============================================================================
# UTILITÁRIOS
# ==============================================================================


def validate_cpf(cpf: str) -> bool:
    cpf = "".join(filter(str.isdigit, cpf))
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
    return "".join(filter(str.isdigit, cpf))


def parse_brazilian_decimal(value: str) -> Decimal:
    if not value:
        return Decimal("0")
    value = re.sub(r"[R$\s]", "", str(value).strip())
    if not value:
        return Decimal("0")
    dots = value.count(".")
    commas = value.count(",")
    if commas == 1 and dots == 0:
        value = value.replace(",", ".")
    elif commas == 1 and dots >= 1:
        value = value.replace(".", "").replace(",", ".")
    elif commas == 0 and dots > 1:
        value = value.replace(".", "")
    try:
        return Decimal(value).quantize(Decimal("0.01"))
    except InvalidOperation:
        raise ValueError(f"Valor monetário inválido: {value}")


# ==============================================================================
# WHATSAPP COM SNAPSHOT (evita race condition)
# ==============================================================================


def _send_whatsapp_with_snapshot(order, method: str):
    """
    Envia notificação usando SNAPSHOT com serialização segura.
    """
    from django.conf import settings

    broker_url = getattr(settings, "CELERY_BROKER_URL", "")
    if not broker_url:
        return

    if not order or not getattr(order, "customer", None):
        return

    # CORREÇÃO CRÍTICA: Uso do DjangoJSONEncoder
    try:
        snapshot = create_order_snapshot(order)
        snapshot_json = json.dumps(snapshot, cls=DjangoJSONEncoder)
    except Exception as e:
        # Mudado para error para visibilidade no Sentry/Logs
        logger.error(
            "[WhatsApp] ERRO FATAL ao criar snapshot order=%s: %s",
            getattr(order, "id", "?"),
            e,
            exc_info=True,
        )
        return

    def _safe_send():
        try:
            send_whatsapp_notification.apply_async(
                args=[snapshot_json, method],
                expires=300,
                ignore_result=True,
            )
        except Exception as e:
            logger.warning("[WhatsApp] Falha ao enviar task order=%s: %s", order.id, e)

    try:
        db_transaction.on_commit(_safe_send)
    except Exception as e:
        logger.warning(
            "[WhatsApp] Falha ao agendar on_commit order=%s: %s", order.id, e
        )


def _send_whatsapp(task, order_id: str):
    """LEGADO: Envia task para Celery."""
    from django.conf import settings

    broker_url = getattr(settings, "CELERY_BROKER_URL", "")
    if not broker_url:
        return

    def _safe_send():
        try:
            task.apply_async(
                args=[order_id],
                expires=300,
                ignore_result=True,
            )
        except Exception as e:
            logger.warning(
                "[WhatsApp] Falha ao enviar legado order=%s: %s", order_id, e
            )

    try:
        db_transaction.on_commit(_safe_send)
    except Exception as e:
        logger.warning(
            "[WhatsApp] Falha ao agendar on_commit legado order=%s: %s", order_id, e
        )


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
        delivery_address = (
            ""
            if delivery_type == DeliveryType.PICKUP
            else data.get("delivery_address", "")
        )

        if delivery_type != DeliveryType.PICKUP and not delivery_address.strip():
            raise ValueError("Endereço obrigatório.")

        sale_date = data.get("sale_date") or timezone.now().date()
        motoboy_fee = (
            data.get("motoboy_fee") if delivery_type == DeliveryType.MOTOBOY else None
        )
        motoboy_paid = (
            data.get("motoboy_paid", False)
            if delivery_type == DeliveryType.MOTOBOY
            else False
        )

        order = Order.objects.create(
            tenant=tenant,
            customer=customer,
            seller=seller,
            total_value=data["total_value"],
            delivery_type=delivery_type,
            delivery_status=DeliveryStatus.PENDING,
            delivery_address=delivery_address,
            notes=data.get("notes", ""),
            is_priority=data.get("is_priority", False),
            sale_date=sale_date,
            motoboy_fee=motoboy_fee,
            motoboy_paid=motoboy_paid,
        )

        OrderActivity.log(
            order=order,
            activity_type=OrderActivity.ActivityType.CREATED,
            description=f"Criado por {seller.get_full_name() or seller.email}",
            user=seller,
            delivery_type=delivery_type,
            total_value=str(order.total_value),
        )

        _send_whatsapp_with_snapshot(order, "send_order_created")
        return order

    @db_transaction.atomic
    def duplicate_order(self, *, order: Order, actor):
        if order.tenant_id != actor.tenant_id:
            raise ValueError("Usuário não pertence ao tenant.")

        new_order = Order.objects.create(
            tenant=order.tenant,
            customer=order.customer,
            seller=actor,
            total_value=order.total_value,
            delivery_type=order.delivery_type,
            delivery_status=DeliveryStatus.PENDING,
            delivery_address=order.delivery_address,
            is_priority=order.is_priority,
            sale_date=timezone.now().date(),
            notes=f"Cópia de {order.code}",
        )

        OrderActivity.log(
            order=new_order,
            activity_type=OrderActivity.ActivityType.CREATED,
            description=f"Duplicado de {order.code}",
            user=actor,
        )

        _send_whatsapp_with_snapshot(new_order, "send_order_created")
        return new_order

    @db_transaction.atomic
    def update_order(self, *, order: Order, actor, data):
        """Atualização centralizada com lock e logging."""
        if order.tenant_id != actor.tenant_id:
            raise ValueError("Usuário não pertence ao tenant.")

        order = Order.objects.select_for_update().get(id=order.id)

        # Atualiza campos permitidos
        if "total_value" in data:
            order.total_value = data["total_value"]
        if "delivery_address" in data:
            order.delivery_address = data["delivery_address"]
        if "notes" in data:
            order.notes = data["notes"]
        if "internal_notes" in data:
            order.internal_notes = data["internal_notes"]
        if "is_priority" in data:
            order.is_priority = data["is_priority"]

        # Campos motoboy (só se for entrega motoboy)
        if order.delivery_type == DeliveryType.MOTOBOY:
            if "motoboy_fee" in data:
                order.motoboy_fee = data["motoboy_fee"]
            if "motoboy_paid" in data:
                order.motoboy_paid = data["motoboy_paid"]

        order.save()

        OrderActivity.log(
            order=order,
            activity_type=OrderActivity.ActivityType.EDITED,
            description="Pedido editado",
            user=actor,
        )
        return order


class OrderStatusService:
    @db_transaction.atomic
    def mark_as_paid(self, *, order: Order, actor):
        if order.tenant_id != actor.tenant_id:
            raise ValueError("Usuário não pertence ao tenant.")
        order = Order.objects.select_for_update().get(id=order.id)
        if order.order_status in [OrderStatus.CANCELLED, OrderStatus.RETURNED]:
            raise ValueError("Não é permitido pagar um pedido cancelado ou devolvido.")
        if order.payment_status == PaymentStatus.PAID:
            return order
        order.payment_status = PaymentStatus.PAID
        if order.order_status == OrderStatus.PENDING:
            order.order_status = OrderStatus.CONFIRMED
        order.save(update_fields=["payment_status", "order_status", "updated_at"])
        OrderActivity.log(
            order=order,
            activity_type=OrderActivity.ActivityType.PAYMENT_RECEIVED,
            description="Pagamento confirmado",
            user=actor,
        )
        _send_whatsapp_with_snapshot(order, "send_payment_received")
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

        # Correção Lógica: Permite reenvio de notificação se o usuário editar rastreio
        # if order.delivery_status == DeliveryStatus.SHIPPED:
        #    return order

        if order.delivery_status not in [
            DeliveryStatus.PENDING,
            DeliveryStatus.FAILED_ATTEMPT,
            DeliveryStatus.SHIPPED,
        ]:
            raise ValueError("Status inválido para envio.")

        if DeliveryType.requires_tracking(order.delivery_type):
            if not tracking_code or not tracking_code.strip():
                raise ValueError(
                    f"Rastreio obrigatório para {order.get_delivery_type_display()}."
                )
            order.tracking_code = tracking_code.strip().upper()
        elif tracking_code:
            order.tracking_code = tracking_code.strip().upper()

        if order.delivery_status != DeliveryStatus.SHIPPED:
            order.delivery_status = DeliveryStatus.SHIPPED
            order.shipped_at = timezone.now()
        if order.order_status == OrderStatus.PENDING:
            order.order_status = OrderStatus.CONFIRMED
        order.save(
            update_fields=[
                "delivery_status",
                "shipped_at",
                "tracking_code",
                "order_status",
                "updated_at",
            ]
        )

        OrderActivity.log(
            order=order,
            activity_type=OrderActivity.ActivityType.SHIPPED,
            description=f"Enviado{f' - {order.tracking_code}' if order.tracking_code else ''}",
            user=actor,
        )

        _send_whatsapp_with_snapshot(order, "send_order_shipped")
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
        if order.delivery_status not in [
            DeliveryStatus.SHIPPED,
            DeliveryStatus.FAILED_ATTEMPT,
        ]:
            raise ValueError("Precisa estar enviado.")
        order.delivery_status = DeliveryStatus.DELIVERED
        order.delivered_at = timezone.now()
        order.order_status = OrderStatus.COMPLETED
        order.save(
            update_fields=[
                "delivery_status",
                "delivered_at",
                "order_status",
                "updated_at",
            ]
        )
        OrderActivity.log(
            order=order,
            activity_type=OrderActivity.ActivityType.DELIVERED,
            description="Entregue",
            user=actor,
        )
        _send_whatsapp_with_snapshot(order, "send_order_delivered")
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
        OrderActivity.log(
            order=order,
            activity_type=OrderActivity.ActivityType.FAILED_ATTEMPT,
            description=f"Tentativa {order.delivery_attempts} falha. {reason}".strip(),
            user=actor,
        )
        _send_whatsapp_with_snapshot(order, "send_delivery_failed")
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

        # Garante geração de código se não houver
        if not order.pickup_code:
            order.pickup_code = order.generate_pickup_code()

        order.delivery_status = DeliveryStatus.READY_FOR_PICKUP
        order.shipped_at = timezone.now()
        order.expires_at = timezone.now() + timedelta(hours=PICKUP_EXPIRY_HOURS)
        if order.order_status == OrderStatus.PENDING:
            order.order_status = OrderStatus.CONFIRMED
        order.save(
            update_fields=[
                "delivery_status",
                "shipped_at",
                "expires_at",
                "order_status",
                "pickup_code",
                "updated_at",
            ]
        )

        OrderActivity.log(
            order=order,
            activity_type=OrderActivity.ActivityType.READY_PICKUP,
            description=f"Pronto. Código: {order.pickup_code}",
            user=actor,
        )
        _send_whatsapp_with_snapshot(order, "send_order_ready_for_pickup")
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
        order.save(
            update_fields=[
                "delivery_status",
                "delivered_at",
                "order_status",
                "expires_at",
                "updated_at",
            ]
        )
        OrderActivity.log(
            order=order,
            activity_type=OrderActivity.ActivityType.PICKED_UP,
            description="Retirado",
            user=actor,
        )
        _send_whatsapp_with_snapshot(order, "send_order_picked_up")
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
        order.save(
            update_fields=[
                "order_status",
                "cancel_reason",
                "cancelled_at",
                "updated_at",
            ]
        )
        OrderActivity.log(
            order=order,
            activity_type=OrderActivity.ActivityType.CANCELLED,
            description=f"Cancelado. {reason}".strip(),
            user=actor,
        )
        _send_whatsapp_with_snapshot(order, "send_order_cancelled")
        return order

    @db_transaction.atomic
    def return_order(
        self, *, order: Order, actor, reason: str = "", refund: bool = False
    ):
        if order.tenant_id != actor.tenant_id:
            raise ValueError("Usuário não pertence ao tenant.")
        order = Order.objects.select_for_update().get(id=order.id)
        if order.order_status != OrderStatus.COMPLETED:
            raise ValueError("Apenas concluídos.")
        if order.delivery_status not in [
            DeliveryStatus.DELIVERED,
            DeliveryStatus.PICKED_UP,
        ]:
            raise ValueError("Precisa ter sido entregue/retirado.")
        order.order_status = OrderStatus.RETURNED
        order.return_reason = reason
        order.returned_at = timezone.now()
        if refund and order.payment_status == PaymentStatus.PAID:
            order.payment_status = PaymentStatus.REFUNDED
        order.save(
            update_fields=[
                "order_status",
                "return_reason",
                "returned_at",
                "payment_status",
                "updated_at",
            ]
        )
        OrderActivity.log(
            order=order,
            activity_type=OrderActivity.ActivityType.RETURNED,
            description=f"Devolvido. {reason}".strip(),
            user=actor,
        )
        if refund:
            OrderActivity.log(
                order=order,
                activity_type=OrderActivity.ActivityType.REFUNDED,
                description="Reembolsado",
                user=actor,
            )
            _send_whatsapp_with_snapshot(order, "send_payment_refunded")
        _send_whatsapp_with_snapshot(order, "send_order_returned")
        return order

    @db_transaction.atomic
    def change_delivery_type(
        self, *, order: Order, actor, new_type: str, address: str = ""
    ):
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

        # Reset de status se mudar de retirada para envio
        if (
            order.delivery_status == DeliveryStatus.READY_FOR_PICKUP
            and new_type != DeliveryType.PICKUP
        ):
            order.delivery_status = DeliveryStatus.PENDING
            order.expires_at = None

        order.delivery_type = new_type
        order.delivery_address = address
        order.tracking_code = ""
        order.save(
            update_fields=[
                "delivery_type",
                "delivery_address",
                "tracking_code",
                "delivery_status",
                "expires_at",
                "updated_at",
            ]
        )
        OrderActivity.log(
            order=order,
            activity_type=OrderActivity.ActivityType.DELIVERY_TYPE_CHANGED,
            description=f"{dict(DeliveryType.choices)[old_type]} -> {dict(DeliveryType.choices)[new_type]}",
            user=actor,
        )
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
        order.save(
            update_fields=[
                "delivery_status",
                "order_status",
                "cancel_reason",
                "cancelled_at",
                "updated_at",
            ]
        )
        OrderActivity.log(
            order=order,
            activity_type=OrderActivity.ActivityType.EXPIRED,
            description=f"Expirado - {PICKUP_EXPIRY_HOURS}h",
            user=None,
        )
        _send_whatsapp_with_snapshot(order, "send_order_expired")
        return order

    def resend_notification(self, *, order: Order, notification_type: str):
        if order.order_status in [OrderStatus.CANCELLED, OrderStatus.RETURNED]:
            if notification_type not in ["cancelled", "returned"]:
                raise ValueError("Não pode enviar para cancelado/devolvido.")

        # Mapeamento para métodos do WhatsAppNotificationService
        method_map = {
            "created": "send_order_created",
            "confirmed": "send_order_confirmed",
            "payment": "send_payment_received",
            "shipped": "send_order_shipped",
            "delivered": "send_order_delivered",
            "ready_pickup": "send_order_ready_for_pickup",
            "picked_up": "send_order_picked_up",
            "cancelled": "send_order_cancelled",
            "returned": "send_order_returned",
        }

        method = method_map.get(notification_type)
        if not method:
            raise ValueError(f"Tipo inválido: {notification_type}")

        # Usa o mecanismo robusto de SNAPSHOT (mesmo para reenvio)
        _send_whatsapp_with_snapshot(order, method)

        OrderActivity.log(
            order=order,
            activity_type=OrderActivity.ActivityType.NOTIFICATION_SENT,
            description=f"Reenviado: {notification_type}",
            user=None,
        )

    @db_transaction.atomic
    def delete_order(self, *, order: Order, actor):
        if order.tenant_id != actor.tenant_id:
            raise ValueError("Usuário não pertence ao tenant.")
        if order.order_status not in [OrderStatus.PENDING, OrderStatus.CANCELLED]:
            raise ValueError("Só pode deletar pedidos pendentes ou cancelados.")
        if order.payment_status == PaymentStatus.PAID:
            raise ValueError("Não pode deletar pedido pago.")
        order_code = order.code
        order.delete()
        return order_code
