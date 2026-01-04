from django.db import transaction as db_transaction

from apps.integrations.whatsapp.tasks import (
    send_order_created_whatsapp,
    send_order_delivered_whatsapp,
    send_order_shipped_whatsapp,
)
from apps.orders.models import (
    Customer,
    DeliveryStatus,
    DeliveryType,
    Order,
    OrderStatus,
)


class OrderService:
    """
    Service responsável pela criação de pedidos.
    """

    @db_transaction.atomic
    def create_order(self, *, tenant, seller, data):
        # Segurança de tenant
        if seller.tenant_id != tenant.id:
            raise ValueError("Usuário não pertence ao tenant.")

        # Normalização do telefone
        phone = data["customer_phone"]
        phone_normalized = "".join(filter(str.isdigit, phone))

        # Cliente único por tenant + telefone
        customer, _ = Customer.objects.for_tenant(tenant).get_or_create(
            phone_normalized=phone_normalized,
            defaults={
                "name": data["customer_name"],
                "phone": phone,
                "tenant": tenant,
            },
        )

        # Tipo de entrega
        delivery_type = data.get("delivery_type", DeliveryType.DELIVERY)

        # Regra clara:
        # - retirada NÃO tem endereço
        # - entrega pode ter endereço
        delivery_address = (
            ""
            if delivery_type == DeliveryType.PICKUP
            else data.get("delivery_address", "")
        )

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

        # 🔔 WhatsApp assíncrono — pedido criado
        send_order_created_whatsapp.delay(str(order.id))

        return order


class OrderStatusService:
    """
    Service responsável por mudanças de status do pedido.
    """

    @db_transaction.atomic
    def mark_as_shipped(self, *, order: Order, actor):
        """
        Marca pedido como enviado (somente para entrega).
        """

        if order.tenant_id != actor.tenant_id:
            raise ValueError("Usuário não pertence ao tenant do pedido.")

        if order.delivery_type != DeliveryType.DELIVERY:
            raise ValueError("Pedido não é do tipo entrega.")

        if order.order_status == OrderStatus.CANCELLED:
            raise ValueError("Pedido cancelado não pode ser enviado.")

        # Idempotência
        if order.delivery_status == DeliveryStatus.SHIPPED:
            return order

        order.delivery_status = DeliveryStatus.SHIPPED
        order.save(update_fields=["delivery_status", "updated_at"])

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

        if order.delivery_type != DeliveryType.DELIVERY:
            raise ValueError("Pedido não é do tipo entrega.")

        if order.delivery_status != DeliveryStatus.SHIPPED:
            raise ValueError("Pedido precisa estar enviado para ser entregue.")

        # Idempotência
        if order.delivery_status == DeliveryStatus.DELIVERED:
            return order

        order.delivery_status = DeliveryStatus.DELIVERED
        order.order_status = OrderStatus.COMPLETED
        order.save(update_fields=["delivery_status", "order_status", "updated_at"])

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

        # WhatsApp específico para retirada pode ser adicionado depois

        return order
