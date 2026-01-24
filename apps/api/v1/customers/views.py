"""
Views de Clientes.
"""

from django.db.models import Q
from rest_framework import viewsets

from apps.api.mixins import TenantViewSetMixin
from apps.orders.models import Customer

from .serializers import (
    CustomerCreateSerializer,
    CustomerListSerializer,
    CustomerSerializer,
)


class CustomerViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """
    CRUD de Clientes.

    list: Lista clientes (filtro por ?search=)
    retrieve: Busca por ID
    create: Cria cliente
    update: Atualiza cliente
    destroy: Remove cliente
    """

    queryset = Customer.objects.all()

    def get_serializer_class(self):
        if self.action == "list":
            return CustomerListSerializer
        if self.action == "create":
            return CustomerCreateSerializer
        return CustomerSerializer

    def get_queryset(self):
        qs = super().get_queryset()

        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(
                Q(name__icontains=search)
                | Q(phone__icontains=search)
                | Q(email__icontains=search)
            )

        return qs.order_by("-created_at")
