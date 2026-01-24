"""
Serializers de Pedidos.
"""

from rest_framework import serializers

from apps.api.v1.customers.serializers import CustomerListSerializer
from apps.orders.models import DeliveryStatus, Order, OrderStatus, PaymentStatus


class OrderSerializer(serializers.ModelSerializer):
    """Serializer completo."""

    customer = CustomerListSerializer(read_only=True)
    seller_name = serializers.CharField(source="seller.get_full_name", read_only=True)
    order_status_display = serializers.CharField(
        source="get_order_status_display", read_only=True
    )
    payment_status_display = serializers.CharField(
        source="get_payment_status_display", read_only=True
    )
    delivery_status_display = serializers.CharField(
        source="get_delivery_status_display", read_only=True
    )

    class Meta:
        model = Order
        fields = [
            "id",
            "code",
            "customer",
            "seller_name",
            "total_value",
            "notes",
            "order_status",
            "order_status_display",
            "payment_status",
            "payment_status_display",
            "delivery_status",
            "delivery_status_display",
            "delivery_type",
            "delivery_address",
            "tracking_code",
            "pickup_code",
            "sale_date",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "code",
            "seller_name",
            "order_status_display",
            "payment_status_display",
            "delivery_status_display",
            "created_at",
            "updated_at",
        ]


class OrderListSerializer(serializers.ModelSerializer):
    """Serializer para listagem."""

    customer_name = serializers.CharField(source="customer.name", read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "code",
            "customer_name",
            "total_value",
            "order_status",
            "payment_status",
            "delivery_status",
            "sale_date",
            "created_at",
        ]


class OrderCreateSerializer(serializers.Serializer):
    """Serializer para criação."""

    # Cliente
    customer_id = serializers.UUIDField(required=False, allow_null=True)
    customer_name = serializers.CharField(max_length=200, required=False)
    customer_phone = serializers.CharField(max_length=20, required=False)
    customer_email = serializers.EmailField(required=False, allow_blank=True)
    customer_cpf = serializers.CharField(
        max_length=14, required=False, allow_blank=True
    )

    # Pedido
    total_value = serializers.DecimalField(max_digits=10, decimal_places=2)
    notes = serializers.CharField(required=False, allow_blank=True)

    # Entrega
    delivery_type = serializers.ChoiceField(
        choices=["pickup", "motoboy", "sedex", "pac"], default="motoboy"
    )
    delivery_address = serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        if not data.get("customer_id"):
            if not data.get("customer_name"):
                raise serializers.ValidationError(
                    {"customer_name": "Obrigatório sem customer_id"}
                )
            if not data.get("customer_phone"):
                raise serializers.ValidationError(
                    {"customer_phone": "Obrigatório sem customer_id"}
                )
        return data


class OrderStatusSerializer(serializers.Serializer):
    """Serializer para atualização de status."""

    order_status = serializers.ChoiceField(choices=OrderStatus.choices, required=False)
    payment_status = serializers.ChoiceField(
        choices=PaymentStatus.choices, required=False
    )
    delivery_status = serializers.ChoiceField(
        choices=DeliveryStatus.choices, required=False
    )
    tracking_code = serializers.CharField(required=False, allow_blank=True)
    cancel_reason = serializers.CharField(required=False, allow_blank=True)
