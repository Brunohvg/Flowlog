"""
Serializers de Pagamentos.
"""

from rest_framework import serializers

from apps.payments.models import PaymentLink


class PaymentLinkSerializer(serializers.ModelSerializer):
    """Serializer completo."""
    
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
            "id", "checkout_url", "status", 
            "paid_at", "created_at", "updated_at",
        ]


class PaymentLinkCreateSerializer(serializers.Serializer):
    """Serializer para criação."""
    
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
                raise serializers.ValidationError({"amount": "Obrigatório sem order_id"})
            if not data.get("customer_name"):
                raise serializers.ValidationError({"customer_name": "Obrigatório sem order_id"})
        return data
