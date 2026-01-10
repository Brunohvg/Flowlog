"""
Views de Pedidos.
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.orders.models import Order
from apps.orders.services import OrderService
from apps.api.mixins import TenantViewSetMixin

from .serializers import (
    OrderSerializer,
    OrderListSerializer,
    OrderCreateSerializer,
    OrderStatusSerializer,
)


class OrderViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """
    CRUD de Pedidos.
    
    Filtros via query params:
    - ?status=pending
    - ?payment=paid
    - ?delivery=shipped
    - ?date_from=2024-01-01
    - ?date_to=2024-01-31
    """
    
    queryset = Order.objects.select_related("customer", "seller")
    
    def get_serializer_class(self):
        if self.action == "list":
            return OrderListSerializer
        if self.action == "create":
            return OrderCreateSerializer
        if self.action == "update_status":
            return OrderStatusSerializer
        return OrderSerializer
    
    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        
        if params.get("status"):
            qs = qs.filter(order_status=params["status"])
        if params.get("payment"):
            qs = qs.filter(payment_status=params["payment"])
        if params.get("delivery"):
            qs = qs.filter(delivery_status=params["delivery"])
        if params.get("date_from"):
            qs = qs.filter(sale_date__gte=params["date_from"])
        if params.get("date_to"):
            qs = qs.filter(sale_date__lte=params["date_to"])
        
        return qs.order_by("-created_at")
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        data = serializer.validated_data
        service = OrderService()
        
        try:
            order = service.create_order(
                tenant=request.tenant,
                seller=request.user,
                data={
                    "customer_id": str(data["customer_id"]) if data.get("customer_id") else None,
                    "customer_name": data.get("customer_name", ""),
                    "customer_phone": data.get("customer_phone", ""),
                    "customer_email": data.get("customer_email", ""),
                    "customer_cpf": data.get("customer_cpf", ""),
                    "total_value": data["total_value"],
                    "notes": data.get("notes", ""),
                    "delivery_type": data.get("delivery_type", "motoboy"),
                    "delivery_address": data.get("delivery_address", ""),
                },
            )
            return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=["patch"], url_path="status")
    def update_status(self, request, pk=None):
        """PATCH /orders/{id}/status/"""
        order = self.get_object()
        serializer = OrderStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        data = serializer.validated_data
        
        for field in ["order_status", "payment_status", "delivery_status", "tracking_code", "cancel_reason"]:
            if field in data:
                setattr(order, field, data[field])
        
        order.save()
        return Response(OrderSerializer(order).data)
