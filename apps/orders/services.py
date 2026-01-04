"""
Services do app orders - Flowlog.
Toda lógica de negócio está aqui. Views são burras.
"""

import logging

from django.db import transaction as db_transaction
from django.utils import timezone

from apps.integrations.whatsapp.tasks import (
    send_order_created_whatsapp,
    send_order_delivered_whatsapp,
    send_order_shipped_whatsapp,
    send_order_ready_for_pickup_whatsapp,
)
from apps.orders.models import (
    Customer,
    DeliveryStatus,
    DeliveryType,
    Order,
    OrderStatus,
    PaymentStatus,
)

logger = logging.getLogger(__name__)


class OrderService:
    """
    Service responsável pela criação de pedidos.
    """

    @db_transaction.atomic
    def create_order(self, *, tenant, seller, data):
        """
        Cria um novo pedido.
        
        Args:
            tenant: Tenant do pedido
            seller: Usuário vendedor
            data: Dados do pedido (dict ou QueryDict)
        
        Returns:
            Order: Pedido criado
            
        Raises:
            ValueError: Se dados inválidos
        """
        # Segurança de tenant
        if seller.tenant_id != tenant.id:
            raise ValueError("Usuário não pertence ao tenant.")

        # Normalização do telefone
        phone = data["customer_phone"]
        phone_normalized = "".join(filter(str.isdigit, phone))
        
        # CPF opcional
        cpf = data.get("customer_cpf", "")
        cpf_normalized = "".join(filter(str.isdigit, cpf)) if cpf else ""

        # Cliente único por tenant + telefone
        customer, created = Customer.objects.for_tenant(tenant).get_or_create(
            phone_normalized=phone_normalized,
            defaults={
                "name": data["customer_name"],
                "phone": phone,
                "cpf": cpf,
                "tenant": tenant,
            },
        )
        
        # Se cliente já existia, atualiza nome e CPF se fornecidos
        if not created:
            updated = False
            # Atualiza nome apenas se for diferente
            if data["customer_name"] and data["customer_name"] != customer.name:
                customer.name = data["customer_name"]
                updated = True
            # Atualiza CPF apenas se fornecido e cliente não tinha
            if cpf and not customer.cpf:
                customer.cpf = cpf
                updated = True
            if updated:
                customer.save()

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
        )

        logger.info(
            "Pedido criado | order=%s | type=%s | customer=%s",
            order.code,
            delivery_type,
            customer.name,
        )

        # 🔔 WhatsApp assíncrono — pedido criado
        send_order_created_whatsapp.delay(str(order.id))

        return order


class OrderStatusService:
    """
    Service responsável por mudanças de status do pedido.
    """

    @db_transaction.atomic
    def mark_as_paid(self, *, order: Order, actor):
        """
        Marca pedido como pago.
        """
        if order.tenant_id != actor.tenant_id:
            raise ValueError("Usuário não pertence ao tenant do pedido.")

        if order.payment_status == PaymentStatus.PAID:
            return order

        order.payment_status = PaymentStatus.PAID

        # Auto-confirma se estava pendente
        if order.order_status == OrderStatus.PENDING:
            order.order_status = OrderStatus.CONFIRMED

        order.save(update_fields=["payment_status", "order_status", "updated_at"])

        logger.info("Pedido marcado como pago | order=%s", order.code)

        return order

    @db_transaction.atomic
    def mark_as_shipped(self, *, order: Order, actor, tracking_code: str = None):
        """
        Marca pedido como enviado.
        
        Args:
            order: Pedido a ser enviado
            actor: Usuário que está executando a ação
            tracking_code: Código de rastreio (obrigatório para Correios)
            
        Returns:
            Order: Pedido atualizado
            
        Raises:
            ValueError: Se não pode ser enviado ou falta rastreio
        """
        if order.tenant_id != actor.tenant_id:
            raise ValueError("Usuário não pertence ao tenant do pedido.")

        # Validação: só entrega pode ser enviada
        if not DeliveryType.is_delivery(order.delivery_type):
            raise ValueError("Pedido de retirada não pode ser enviado.")

        if order.order_status == OrderStatus.CANCELLED:
            raise ValueError("Pedido cancelado não pode ser enviado.")

        # Idempotência
        if order.delivery_status == DeliveryStatus.SHIPPED:
            return order

        if order.delivery_status != DeliveryStatus.PENDING:
            raise ValueError("Pedido não está pendente para envio.")

        # Validação: Correios exige código de rastreio
        if DeliveryType.requires_tracking(order.delivery_type):
            if not tracking_code or not tracking_code.strip():
                raise ValueError(
                    f"Código de rastreio é obrigatório para {order.get_delivery_type_display()}."
                )
            order.tracking_code = tracking_code.strip().upper()

        elif tracking_code:
            # Motoboy: rastreio é opcional, mas se informado, salva
            order.tracking_code = tracking_code.strip().upper()

        order.delivery_status = DeliveryStatus.SHIPPED
        order.shipped_at = timezone.now()

        # Auto-confirma se estava pendente
        if order.order_status == OrderStatus.PENDING:
            order.order_status = OrderStatus.CONFIRMED

        order.save(update_fields=[
            "delivery_status",
            "order_status",
            "tracking_code",
            "shipped_at",
            "updated_at",
        ])

        logger.info(
            "Pedido enviado | order=%s | type=%s | tracking=%s",
            order.code,
            order.delivery_type,
            order.tracking_code or "N/A",
        )

        # 🔔 WhatsApp assíncrono
        send_order_shipped_whatsapp.delay(str(order.id))

        return order

    @db_transaction.atomic
    def mark_as_delivered(self, *, order: Order, actor):
        """
        Marca pedido como entregue (somente entrega).
        """
        if order.tenant_id != actor.tenant_id:
            raise ValueError("Usuário não pertence ao tenant do pedido.")

        if not DeliveryType.is_delivery(order.delivery_type):
            raise ValueError("Pedido de retirada não pode ser marcado como entregue.")

        if order.delivery_status != DeliveryStatus.SHIPPED:
            raise ValueError("Pedido precisa estar enviado para ser entregue.")

        # Idempotência
        if order.delivery_status == DeliveryStatus.DELIVERED:
            return order

        order.delivery_status = DeliveryStatus.DELIVERED
        order.order_status = OrderStatus.COMPLETED
        order.delivered_at = timezone.now()

        order.save(update_fields=[
            "delivery_status",
            "order_status",
            "delivered_at",
            "updated_at",
        ])

        logger.info("Pedido entregue | order=%s", order.code)

        # 🔔 WhatsApp assíncrono
        send_order_delivered_whatsapp.delay(str(order.id))

        return order

    @db_transaction.atomic
    def mark_ready_for_pickup(self, *, order: Order, actor):
        """
        Marca pedido como pronto para retirada (somente retirada).
        """
        if order.tenant_id != actor.tenant_id:
            raise ValueError("Usuário não pertence ao tenant do pedido.")

        if order.delivery_type != DeliveryType.PICKUP:
            raise ValueError("Pedido não é para retirada.")

        # Idempotência
        if order.delivery_status == DeliveryStatus.READY_FOR_PICKUP:
            return order

        order.delivery_status = DeliveryStatus.READY_FOR_PICKUP
        order.order_status = OrderStatus.CONFIRMED

        order.save(update_fields=["delivery_status", "order_status", "updated_at"])

        logger.info("Pedido pronto para retirada | order=%s", order.code)

        # 🔔 WhatsApp assíncrono
        send_order_ready_for_pickup_whatsapp.delay(str(order.id))

        return order

    @db_transaction.atomic
    def mark_as_picked_up(self, *, order: Order, actor):
        """
        Marca pedido como retirado pelo cliente (somente retirada).
        """
        if order.tenant_id != actor.tenant_id:
            raise ValueError("Usuário não pertence ao tenant do pedido.")

        if order.delivery_type != DeliveryType.PICKUP:
            raise ValueError("Pedido não é para retirada.")

        if order.delivery_status != DeliveryStatus.READY_FOR_PICKUP:
            raise ValueError("Pedido precisa estar pronto para retirada.")

        # Idempotência
        if order.delivery_status == DeliveryStatus.PICKED_UP:
            return order

        order.delivery_status = DeliveryStatus.PICKED_UP
        order.order_status = OrderStatus.COMPLETED
        order.delivered_at = timezone.now()  # Usa mesmo campo para consistência

        order.save(update_fields=[
            "delivery_status",
            "order_status",
            "delivered_at",
            "updated_at",
        ])

        logger.info("Pedido retirado | order=%s", order.code)

        return order

    @db_transaction.atomic
    def cancel_order(self, *, order: Order, actor, reason: str = None):
        """
        Cancela um pedido.
        """
        if order.tenant_id != actor.tenant_id:
            raise ValueError("Usuário não pertence ao tenant do pedido.")

        if not order.can_be_cancelled:
            raise ValueError("Este pedido não pode ser cancelado.")

        order.order_status = OrderStatus.CANCELLED

        if reason:
            order.notes = f"{order.notes}\n\n[CANCELADO] {reason}".strip()

        order.save(update_fields=["order_status", "notes", "updated_at"])

        logger.info("Pedido cancelado | order=%s | reason=%s", order.code, reason or "N/A")

        return order
