"""
Serializers de Clientes.
"""

from rest_framework import serializers

from apps.orders.models import Customer


class CustomerSerializer(serializers.ModelSerializer):
    """Serializer completo."""
    
    class Meta:
        model = Customer
        fields = [
            "id", "name", "phone", "phone_normalized", 
            "email", "cpf", "notes", "is_blocked",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "phone_normalized", "created_at", "updated_at"]


class CustomerListSerializer(serializers.ModelSerializer):
    """Serializer para listagem."""
    
    class Meta:
        model = Customer
        fields = ["id", "name", "phone", "email"]


class CustomerCreateSerializer(serializers.ModelSerializer):
    """Serializer para criação."""
    
    class Meta:
        model = Customer
        fields = ["name", "phone", "email", "cpf", "notes"]
