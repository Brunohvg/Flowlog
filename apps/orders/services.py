"""
Services do app orders - Flowlog.
Toda lógica de negócio está aqui. Views são burras.
"""

import logging
from datetime import timedelta

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
    send_order_expired_whatsapp,
    send_order_cancelled_whatsapp,
    send_order_returned_whatsapp,
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

# Tempo padrão para expiração de retiradas (48 horas)
PICKUP_EXPIRY_HOURS = 48


def _safe_send_whatsapp(task, order_id: str, task_name: str = "whatsapp"):
    """
    Envia task do Celery de forma segura.
    Se Redis não estiver disponível, apenas loga e continua.
    """
    from django.conf import settings
    
    # Em modo DEBUG, pula notificações (dev local sem Redis)
    if getattr(settings, 'DEBUG', False):
        logger.debug("DEBUG=True, pulando notificação %s", task_name)
        return
    
    # Se não tem broker configurado, pula
    broker_url = getattr(settings, 'CELERY_BROKER_URL', '')
    if not broker_url:
        logger.debug("Celery não configurado, pulando notificação %s", task_name)
        return
    
    try:
        task.apply_async(args=[order_id], expires=60)
    except Exception as e:
        logger.debug("Redis indisponível para task %s: %s", task_name, type(e).__name__)


class OrderService:
    """
    Service responsável pela criação de pedidos.
    """

    @db_transaction.atomic
    def create_order(self, *, tenant, seller, data):
        """
        Cria um novo pedido.
        """
        if seller.tenant_id != tenant.id:
            raise ValueError("Usuário não pertence ao tenant.")

        # Normalização do telefone
        phone = data["customer_phone"]
        phone_normalized = "".join(filter(str.isdigit, phone))
        
        # CPF opcional
        cpf = data.get("customer_cpf", "")

        # Cliente único por tenant + telefone
        # IMPORTANTE: Inclui tenant no lookup para evitar duplicação
        customer, created = Customer.objects.get_or_create(
            tenant=tenant,
            phone_normalized=phone_normalized,
            defaults={
                "name": data["customer_name"],
                "phone": phone,
                "cpf": cpf,
            },
        )
        
        # Se cliente já existia, atualiza nome e CPF se fornecidos
        if not created:
            updated = False
            if data["customer_name"] and data["customer_name"] != customer.name:
                customer.name = data["customer_name"]
                updated = True
            if cpf and not customer.cpf:
                customer.cpf = cpf
                updated = True
            if updated:
                customer.save()
        
        # Verificar se cliente está bloqueado
        if customer.is_blocked:
            raise ValueError("Este cliente está bloqueado e não pode fazer pedidos.")

        # Tipo de entrega
        delivery_type = data.get("delivery_type", DeliveryType.MOTOBOY)

        # Validação: retirada NÃO tem endereço
        if delivery_type == DeliveryType.PICKUP:
            delivery_address = ""
        else:
            delivery_address = data.get("delivery_address", "")
            if not delivery_address.strip():
                raise ValueError("Endereço de entrega é obrigatório para este tipo de envio.")

        # Criação do pedido
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
        )

        # Log de atividade
        OrderActivity.log(
            order=order,
            activity_type=OrderActivity.ActivityType.CREATED,
            description=f"Pedido criado por {seller.get_full_name() or seller.email}",
            user=seller,
            delivery_type=delivery_type,
            total_value=str(order.total_value),
        )

        logger.info(
            "Pedido criado | order=%s | type=%s | customer=%s",
            order.code, delivery_type, customer.name,
        )

        # 🔔 WhatsApp assíncrono
        _safe_send_whatsapp(send_order_created_whatsapp, str(order.id), "order_created")

        return order

    @db_transaction.atomic
    def duplicate_order(self, *, order: Order, actor):
        """
        Duplica um pedido existente.
        """
        if order.tenant_id != actor.tenant_id:
            raise ValueError("Usuário não pertence ao tenant do pedido.")

        new_order = Order.objects.create(
            tenant=order.tenant,
            customer=order.customer,
            seller=actor,
            total_value=order.total_value,
            delivery_type=order.delivery_type,
            delivery_status=DeliveryStatus.PENDING,
            delivery_address=order.delivery_address,
            notes=f"Cópia de {order.code}",
        )

        OrderActivity.log(
            order=new_order,
            activity_type=OrderActivity.ActivityType.CREATED,
            description=f"Pedido duplicado de {order.code}",
            user=actor,
            original_order=order.code,
        )

        logger.info("Pedido duplicado | original=%s | new=%s", order.code, new_order.code)

        return new_order


class OrderStatusService:
    """
    Service responsável por mudanças de status do pedido.
    """

    @db_transaction.atomic
    def mark_as_paid(self, *, order: Order, actor):
        """Marca pedido como pago."""
        if order.tenant_id != actor.tenant_id:
            raise ValueError("Usuário não pertence ao tenant do pedido.")

        if order.payment_status == PaymentStatus.PAID:
            return order

        old_status = order.payment_status
        order.payment_status = PaymentStatus.PAID

        if order.order_status == OrderStatus.PENDING:
            order.order_status = OrderStatus.CONFIRMED

        order.save(update_fields=["payment_status", "order_status", "updated_at"])

        OrderActivity.log(
            order=order,
            activity_type=OrderActivity.ActivityType.PAYMENT_RECEIVED,
            description="Pagamento confirmado",
            user=actor,
            old_status=old_status,
        )

        logger.info("Pedido marcado como pago | order=%s", order.code)
        
        # 🔔 WhatsApp
        _safe_send_whatsapp(send_payment_received_whatsapp, str(order.id), "payment_received")
        
        return order

    @db_transaction.atomic
    def mark_as_shipped(self, *, order: Order, actor, tracking_code: str = None):
        """Marca pedido como enviado."""
        if order.tenant_id != actor.tenant_id:
            raise ValueError("Usuário não pertence ao tenant do pedido.")

        if not DeliveryType.is_delivery(order.delivery_type):
            raise ValueError("Pedido de retirada não pode ser enviado.")

        if order.order_status in [OrderStatus.CANCELLED, OrderStatus.RETURNED]:
            raise ValueError("Pedido cancelado/devolvido não pode ser enviado.")

        if order.delivery_status == DeliveryStatus.SHIPPED:
            return order

        if order.delivery_status not in [DeliveryStatus.PENDING, DeliveryStatus.FAILED_ATTEMPT]:
            raise ValueError("Pedido não está em status válido para envio.")

        if DeliveryType.requires_tracking(order.delivery_type):
            if not tracking_code or not tracking_code.strip():
                raise ValueError(f"Código de rastreio é obrigatório para {order.get_delivery_type_display()}.")
            order.tracking_code = tracking_code.strip().upper()
        elif tracking_code:
            order.tracking_code = tracking_code.strip().upper()

        order.delivery_status = DeliveryStatus.SHIPPED
        order.shipped_at = timezone.now()

        if order.order_status == OrderStatus.PENDING:
            order.order_status = OrderStatus.CONFIRMED

        order.save(update_fields=[
            "delivery_status", "shipped_at", "tracking_code", "order_status", "updated_at"
        ])

        OrderActivity.log(
            order=order,
            activity_type=OrderActivity.ActivityType.SHIPPED,
            description=f"Pedido enviado{f' - Rastreio: {order.tracking_code}' if order.tracking_code else ''}",
            user=actor,
            tracking_code=order.tracking_code,
        )

        logger.info("Pedido enviado | order=%s | tracking=%s", order.code, order.tracking_code)

        _safe_send_whatsapp(send_order_shipped_whatsapp, str(order.id), "order_shipped")
        return order

    @db_transaction.atomic
    def mark_as_delivered(self, *, order: Order, actor):
        """Marca pedido como entregue."""
        if order.tenant_id != actor.tenant_id:
            raise ValueError("Usuário não pertence ao tenant do pedido.")

        if not DeliveryType.is_delivery(order.delivery_type):
            raise ValueError("Pedido de retirada não pode ser marcado como entregue.")

        if order.delivery_status == DeliveryStatus.DELIVERED:
            return order

        if order.delivery_status not in [DeliveryStatus.SHIPPED, DeliveryStatus.FAILED_ATTEMPT]:
            raise ValueError("Pedido precisa estar enviado para ser entregue.")

        order.delivery_status = DeliveryStatus.DELIVERED
        order.delivered_at = timezone.now()
        order.order_status = OrderStatus.COMPLETED

        order.save(update_fields=["delivery_status", "delivered_at", "order_status", "updated_at"])

        OrderActivity.log(
            order=order,
            activity_type=OrderActivity.ActivityType.DELIVERED,
            description="Pedido entregue ao cliente",
            user=actor,
        )

        logger.info("Pedido entregue | order=%s", order.code)

        _safe_send_whatsapp(send_order_delivered_whatsapp, str(order.id), "order_delivered")
        return order

    @db_transaction.atomic
    def mark_failed_attempt(self, *, order: Order, actor, reason: str = ""):
        """Marca tentativa de entrega falha."""
        if order.tenant_id != actor.tenant_id:
            raise ValueError("Usuário não pertence ao tenant do pedido.")

        if order.delivery_status != DeliveryStatus.SHIPPED:
            raise ValueError("Pedido precisa estar enviado.")

        order.delivery_status = DeliveryStatus.FAILED_ATTEMPT
        order.delivery_attempts += 1

        order.save(update_fields=["delivery_status", "delivery_attempts", "updated_at"])

        OrderActivity.log(
            order=order,
            activity_type=OrderActivity.ActivityType.FAILED_ATTEMPT,
            description=f"Tentativa {order.delivery_attempts} de entrega falha. {reason}".strip(),
            user=actor,
            attempt_number=order.delivery_attempts,
            reason=reason,
        )

        logger.info("Tentativa de entrega falha | order=%s | attempt=%d", order.code, order.delivery_attempts)
        
        # 🔔 WhatsApp
        _safe_send_whatsapp(send_delivery_failed_whatsapp, str(order.id), "delivery_failed")
        
        return order

    @db_transaction.atomic
    def mark_ready_for_pickup(self, *, order: Order, actor):
        """Marca pedido como pronto para retirada."""
        if order.tenant_id != actor.tenant_id:
            raise ValueError("Usuário não pertence ao tenant do pedido.")

        if order.delivery_type != DeliveryType.PICKUP:
            raise ValueError("Apenas pedidos de retirada podem usar esta ação.")

        if order.order_status in [OrderStatus.CANCELLED, OrderStatus.RETURNED]:
            raise ValueError("Pedido cancelado/devolvido.")

        if order.delivery_status == DeliveryStatus.READY_FOR_PICKUP:
            return order

        if order.delivery_status != DeliveryStatus.PENDING:
            raise ValueError("Pedido não está pendente.")

        # Gera código de retirada de 4 dígitos
        order.pickup_code = order.generate_pickup_code()
        
        order.delivery_status = DeliveryStatus.READY_FOR_PICKUP
        order.shipped_at = timezone.now()
        # Define expiração em 48 horas
        order.expires_at = timezone.now() + timedelta(hours=PICKUP_EXPIRY_HOURS)

        if order.order_status == OrderStatus.PENDING:
            order.order_status = OrderStatus.CONFIRMED

        order.save(update_fields=[
            "delivery_status", "shipped_at", "expires_at", "order_status", 
            "pickup_code", "updated_at"
        ])

        OrderActivity.log(
            order=order,
            activity_type=OrderActivity.ActivityType.READY_PICKUP,
            description=f"Pedido pronto para retirada. Código: {order.pickup_code}. Expira em {PICKUP_EXPIRY_HOURS}h.",
            user=actor,
            pickup_code=order.pickup_code,
            expires_at=order.expires_at.isoformat(),
        )

        logger.info(
            "Pedido pronto para retirada | order=%s | pickup_code=%s | expires=%s", 
            order.code, order.pickup_code, order.expires_at
        )

        _safe_send_whatsapp(send_order_ready_for_pickup_whatsapp, str(order.id), "ready_for_pickup")
        return order

    @db_transaction.atomic
    def mark_as_picked_up(self, *, order: Order, actor):
        """Marca pedido como retirado."""
        if order.tenant_id != actor.tenant_id:
            raise ValueError("Usuário não pertence ao tenant do pedido.")

        if order.delivery_type != DeliveryType.PICKUP:
            raise ValueError("Apenas pedidos de retirada podem usar esta ação.")

        if order.delivery_status == DeliveryStatus.PICKED_UP:
            return order

        if order.delivery_status != DeliveryStatus.READY_FOR_PICKUP:
            raise ValueError("Pedido precisa estar pronto para retirada.")

        order.delivery_status = DeliveryStatus.PICKED_UP
        order.delivered_at = timezone.now()
        order.order_status = OrderStatus.COMPLETED
        order.expires_at = None  # Limpa expiração

        order.save(update_fields=[
            "delivery_status", "delivered_at", "order_status", "expires_at", "updated_at"
        ])

        OrderActivity.log(
            order=order,
            activity_type=OrderActivity.ActivityType.PICKED_UP,
            description="Pedido retirado pelo cliente",
            user=actor,
        )

        logger.info("Pedido retirado | order=%s", order.code)

        # 🔔 WhatsApp
        _safe_send_whatsapp(send_order_picked_up_whatsapp, str(order.id), "picked_up")
        
        return order

    @db_transaction.atomic
    def cancel_order(self, *, order: Order, actor, reason: str = ""):
        """Cancela um pedido."""
        if order.tenant_id != actor.tenant_id:
            raise ValueError("Usuário não pertence ao tenant do pedido.")

        if order.order_status == OrderStatus.CANCELLED:
            return order

        if order.order_status == OrderStatus.RETURNED:
            raise ValueError("Pedido devolvido não pode ser cancelado.")

        old_status = order.order_status
        order.order_status = OrderStatus.CANCELLED
        order.cancel_reason = reason
        order.cancelled_at = timezone.now()

        order.save(update_fields=[
            "order_status", "cancel_reason", "cancelled_at", "updated_at"
        ])

        OrderActivity.log(
            order=order,
            activity_type=OrderActivity.ActivityType.CANCELLED,
            description=f"Pedido cancelado. {reason}".strip(),
            user=actor,
            old_status=old_status,
            reason=reason,
        )

        logger.info("Pedido cancelado | order=%s | reason=%s", order.code, reason)
        
        # 🔔 WhatsApp
        _safe_send_whatsapp(send_order_cancelled_whatsapp, str(order.id), "cancelled")
        
        return order

    @db_transaction.atomic
    def return_order(self, *, order: Order, actor, reason: str = "", refund: bool = False):
        """Processa devolução de um pedido."""
        if order.tenant_id != actor.tenant_id:
            raise ValueError("Usuário não pertence ao tenant do pedido.")

        if order.order_status != OrderStatus.COMPLETED:
            raise ValueError("Apenas pedidos concluídos podem ser devolvidos.")

        if order.delivery_status not in [DeliveryStatus.DELIVERED, DeliveryStatus.PICKED_UP]:
            raise ValueError("Pedido precisa ter sido entregue/retirado.")

        order.order_status = OrderStatus.RETURNED
        order.return_reason = reason
        order.returned_at = timezone.now()

        if refund and order.payment_status == PaymentStatus.PAID:
            order.payment_status = PaymentStatus.REFUNDED

        order.save(update_fields=[
            "order_status", "return_reason", "returned_at", "payment_status", "updated_at"
        ])

        OrderActivity.log(
            order=order,
            activity_type=OrderActivity.ActivityType.RETURNED,
            description=f"Pedido devolvido. {reason}".strip(),
            user=actor,
            reason=reason,
            refunded=refund,
        )

        if refund:
            OrderActivity.log(
                order=order,
                activity_type=OrderActivity.ActivityType.REFUNDED,
                description="Reembolso processado",
                user=actor,
            )
            # 🔔 WhatsApp - notifica estorno
            _safe_send_whatsapp(send_payment_refunded_whatsapp, str(order.id), "payment_refunded")

        logger.info("Pedido devolvido | order=%s | refund=%s", order.code, refund)
        
        # 🔔 WhatsApp - notifica devolução
        _safe_send_whatsapp(send_order_returned_whatsapp, str(order.id), "returned")
        
        return order

    @db_transaction.atomic
    def change_delivery_type(self, *, order: Order, actor, new_type: str, address: str = ""):
        """Altera o tipo de entrega do pedido."""
        if order.tenant_id != actor.tenant_id:
            raise ValueError("Usuário não pertence ao tenant do pedido.")

        if not order.can_change_delivery_type:
            raise ValueError("Não é possível alterar o tipo de entrega neste momento.")

        old_type = order.delivery_type

        # Validações
        if new_type == DeliveryType.PICKUP:
            address = ""
        elif DeliveryType.requires_address(new_type) and not address.strip():
            raise ValueError("Endereço é obrigatório para este tipo de entrega.")

        # Se estava pronto para retirada e mudou para entrega, volta para pendente
        if order.delivery_status == DeliveryStatus.READY_FOR_PICKUP and new_type != DeliveryType.PICKUP:
            order.delivery_status = DeliveryStatus.PENDING
            order.expires_at = None

        order.delivery_type = new_type
        order.delivery_address = address
        order.tracking_code = ""  # Limpa rastreio antigo

        order.save(update_fields=[
            "delivery_type", "delivery_address", "tracking_code", "delivery_status", "expires_at", "updated_at"
        ])

        OrderActivity.log(
            order=order,
            activity_type=OrderActivity.ActivityType.DELIVERY_TYPE_CHANGED,
            description=f"Tipo de entrega alterado de {dict(DeliveryType.choices)[old_type]} para {dict(DeliveryType.choices)[new_type]}",
            user=actor,
            old_type=old_type,
            new_type=new_type,
        )

        logger.info("Tipo de entrega alterado | order=%s | %s -> %s", order.code, old_type, new_type)
        return order

    @db_transaction.atomic
    def expire_pickup_order(self, *, order: Order):
        """Expira pedido de retirada não realizada (chamado por task)."""
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

        order.save(update_fields=[
            "delivery_status", "order_status", "cancel_reason", "cancelled_at", "updated_at"
        ])

        OrderActivity.log(
            order=order,
            activity_type=OrderActivity.ActivityType.EXPIRED,
            description=f"Pedido expirado - retirada não realizada em {PICKUP_EXPIRY_HOURS}h",
            user=None,
        )

        logger.info("Pedido expirado | order=%s", order.code)
        return order

    def resend_notification(self, *, order: Order, notification_type: str):
        """Reenvia notificação WhatsApp."""
        if order.order_status in [OrderStatus.CANCELLED, OrderStatus.RETURNED]:
            if notification_type not in ["cancelled", "returned"]:
                raise ValueError("Não é possível enviar notificação para pedido cancelado/devolvido.")

        notification_tasks = {
            "created": send_order_created_whatsapp,
            "confirmed": send_order_confirmed_whatsapp,
            "payment": send_payment_received_whatsapp,
            "shipped": send_order_shipped_whatsapp,
            "delivered": send_order_delivered_whatsapp,
            "ready_pickup": send_order_ready_for_pickup_whatsapp,
            "picked_up": send_order_picked_up_whatsapp,
            "cancelled": send_order_cancelled_whatsapp,
            "returned": send_order_returned_whatsapp,
        }
        
        task = notification_tasks.get(notification_type)
        if not task:
            raise ValueError(f"Tipo de notificação inválido: {notification_type}")
        
        _safe_send_whatsapp(task, str(order.id), notification_type)

        OrderActivity.log(
            order=order,
            activity_type=OrderActivity.ActivityType.NOTIFICATION_SENT,
            description=f"Notificação reenviada: {notification_type}",
            user=None,
            notification_type=notification_type,
        )

        logger.info("Notificação reenviada | order=%s | type=%s", order.code, notification_type)
