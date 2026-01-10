"""
Serializers da API v1 - Flowlog
"""

from rest_framework import serializers

from apps.orders.models import Customer, Order, OrderStatus, PaymentStatus, DeliveryStatus
from apps.payments.models import PaymentLink


# ==============================================================================
# CUSTOMER
# ==============================================================================

class CustomerSerializer(serializers.ModelSerializer):
    """Serializer completo do Cliente"""
    
    class Meta:
        model = Customer
        fields = [
            "id", "name", "phone", "phone_normalized", "email",
            "cpf", "notes", "is_blocked",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "phone_normalized", "created_at", "updated_at"]


class CustomerListSerializer(serializers.ModelSerializer):
    """Serializer resumido para listagens"""
    
    class Meta:
        model = Customer
        fields = ["id", "name", "phone", "email"]


class CustomerCreateSerializer(serializers.ModelSerializer):
    """Serializer para criação de cliente"""
    
    class Meta:
        model = Customer
        fields = ["name", "phone", "email", "cpf", "notes"]


# ==============================================================================
# ORDER
# ==============================================================================

class OrderSerializer(serializers.ModelSerializer):
    """Serializer completo do Pedido"""
    
    customer = CustomerListSerializer(read_only=True)
    customer_id = serializers.UUIDField(write_only=True, required=False)
    seller_name = serializers.CharField(source="seller.get_full_name", read_only=True)
    
    order_status_display = serializers.CharField(source="get_order_status_display", read_only=True)
    payment_status_display = serializers.CharField(source="get_payment_status_display", read_only=True)
    delivery_status_display = serializers.CharField(source="get_delivery_status_display", read_only=True)
    
    class Meta:
        model = Order
        fields = [
            "id", "code", "customer", "customer_id",
            "seller_name", "total_value", "notes",
            "order_status", "order_status_display",
            "payment_status", "payment_status_display",
            "delivery_status", "delivery_status_display",
            "delivery_type", "delivery_address",
            "tracking_code", "pickup_code",
            "sale_date", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "code", "seller_name", "created_at", "updated_at",
            "order_status_display", "payment_status_display", "delivery_status_display",
        ]


class OrderListSerializer(serializers.ModelSerializer):
    """Serializer resumido para listagens"""
    
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    
    class Meta:
        model = Order
        fields = [
            "id", "code", "customer_name", "total_value",
            "order_status", "payment_status", "delivery_status",
            "sale_date", "created_at",
        ]


class OrderCreateSerializer(serializers.Serializer):
    """Serializer para criação de pedido"""
    
    # Cliente (existente ou novo)
    customer_id = serializers.UUIDField(required=False, allow_null=True)
    customer_name = serializers.CharField(max_length=200, required=False)
    customer_phone = serializers.CharField(max_length=20, required=False)
    customer_email = serializers.EmailField(required=False, allow_blank=True)
    customer_cpf = serializers.CharField(max_length=14, required=False, allow_blank=True)
    
    # Pedido
    total_value = serializers.DecimalField(max_digits=10, decimal_places=2)
    notes = serializers.CharField(required=False, allow_blank=True)
    
    # Entrega
    delivery_type = serializers.ChoiceField(choices=["pickup", "motoboy", "sedex", "pac"], default="motoboy")
    delivery_address = serializers.CharField(required=False, allow_blank=True)
    
    def validate(self, data):
        if not data.get("customer_id") and not data.get("customer_name"):
            raise serializers.ValidationError({"customer_name": "Informe customer_id ou customer_name"})
        if not data.get("customer_id") and not data.get("customer_phone"):
            raise serializers.ValidationError({"customer_phone": "Informe customer_id ou customer_phone"})
        return data


class OrderStatusUpdateSerializer(serializers.Serializer):
    """Serializer para atualização de status"""
    
    order_status = serializers.ChoiceField(choices=OrderStatus.choices, required=False)
    payment_status = serializers.ChoiceField(choices=PaymentStatus.choices, required=False)
    delivery_status = serializers.ChoiceField(choices=DeliveryStatus.choices, required=False)
    tracking_code = serializers.CharField(required=False, allow_blank=True)
    cancel_reason = serializers.CharField(required=False, allow_blank=True)


# ==============================================================================
# PAYMENT LINK
# ==============================================================================

class PaymentLinkSerializer(serializers.ModelSerializer):
    """Serializer do Link de Pagamento"""
    
    order_code = serializers.CharField(source="order.code", read_only=True, allow_null=True)
    
    class Meta:
        model = PaymentLink
        fields = [
            "id", "order", "order_code",
            "checkout_url", "amount", "installments",
            "status", "description",
            "customer_name", "customer_phone", "customer_email",
            "paid_at", "expires_at",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "checkout_url", "status", "paid_at",
            "created_at", "updated_at", "order_code",
        ]


class PaymentLinkCreateSerializer(serializers.Serializer):
    """Serializer para criar link de pagamento"""
    
    order_id = serializers.UUIDField(required=False, allow_null=True)
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    installments = serializers.IntegerField(min_value=1, max_value=12, default=1)
    description = serializers.CharField(max_length=200, required=False)
    customer_name = serializers.CharField(max_length=200, required=False)
    customer_phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    customer_email = serializers.EmailField(required=False, allow_blank=True)
    
    def validate(self, data):
        if not data.get("order_id"):
            if not data.get("amount"):
                raise serializers.ValidationError({"amount": "Informe order_id ou amount"})
            if not data.get("customer_name"):
                raise serializers.ValidationError({"customer_name": "Informe order_id ou customer_name"})
        return data


# ==============================================================================
# DASHBOARD / STATS
# ==============================================================================

class DashboardStatsSerializer(serializers.Serializer):
    """Serializer para estatísticas do dashboard"""
    
    orders_today = serializers.IntegerField()
    orders_pending = serializers.IntegerField()
    orders_month = serializers.IntegerField()
    revenue_today = serializers.DecimalField(max_digits=12, decimal_places=2)
    revenue_month = serializers.DecimalField(max_digits=12, decimal_places=2)
    ticket_medio = serializers.DecimalField(max_digits=10, decimal_places=2)
