"""
Filtros de Pedidos.
"""

from django.db import models
from django_filters import rest_framework as filters

from apps.orders.models import Order, OrderStatus, PaymentStatus, DeliveryStatus


class OrderFilter(filters.FilterSet):
    """
    Filtros para listagem de pedidos.
    
    Exemplos:
        /api/v1/orders/?status=pending
        /api/v1/orders/?payment=paid
        /api/v1/orders/?delivery=shipped
        /api/v1/orders/?date_from=2024-01-01&date_to=2024-01-31
        /api/v1/orders/?customer=uuid
        /api/v1/orders/?search=FL-001
    """
    
    status = filters.ChoiceFilter(
        field_name="order_status",
        choices=OrderStatus.choices,
        label="Status do Pedido"
    )
    
    payment = filters.ChoiceFilter(
        field_name="payment_status",
        choices=PaymentStatus.choices,
        label="Status de Pagamento"
    )
    
    delivery = filters.ChoiceFilter(
        field_name="delivery_status",
        choices=DeliveryStatus.choices,
        label="Status de Entrega"
    )
    
    date_from = filters.DateFilter(
        field_name="sale_date",
        lookup_expr="gte",
        label="Data inicial"
    )
    
    date_to = filters.DateFilter(
        field_name="sale_date",
        lookup_expr="lte",
        label="Data final"
    )
    
    customer = filters.UUIDFilter(
        field_name="customer_id",
        label="ID do Cliente"
    )
    
    search = filters.CharFilter(
        method="filter_search",
        label="Busca (código ou cliente)"
    )
    
    min_value = filters.NumberFilter(
        field_name="total_value",
        lookup_expr="gte",
        label="Valor mínimo"
    )
    
    max_value = filters.NumberFilter(
        field_name="total_value",
        lookup_expr="lte",
        label="Valor máximo"
    )
    
    class Meta:
        model = Order
        fields = []
    
    def filter_search(self, queryset, name, value):
        """Busca por código do pedido ou nome do cliente."""
        return queryset.filter(
            models.Q(code__icontains=value) |
            models.Q(customer__name__icontains=value)
        )
