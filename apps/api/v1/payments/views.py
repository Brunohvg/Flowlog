"""
Views de Pagamentos.
"""

from rest_framework import viewsets, status, mixins
from rest_framework.response import Response

from apps.orders.models import Order
from apps.payments.models import PaymentLink
from apps.payments.services import (
    create_payment_link_for_order,
    create_standalone_payment_link,
    PagarmeError,
)
from apps.api.mixins import TenantViewSetMixin

from .serializers import PaymentLinkSerializer, PaymentLinkCreateSerializer


class PaymentLinkViewSet(
    TenantViewSetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet
):
    """
    Links de Pagamento.
    
    list: Lista links
    retrieve: Busca por ID
    create: Cria link (para pedido ou avulso)
    
    Filtros:
    - ?status=pending
    - ?status=paid
    """
    
    queryset = PaymentLink.objects.select_related("order")
    
    def get_serializer_class(self):
        if self.action == "create":
            return PaymentLinkCreateSerializer
        return PaymentLinkSerializer
    
    def get_queryset(self):
        qs = super().get_queryset()
        
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        
        return qs.order_by("-created_at")
    
    def create(self, request, *args, **kwargs):
        serializer = PaymentLinkCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        data = serializer.validated_data
        
        try:
            if data.get("order_id"):
                order = Order.objects.for_tenant(request.tenant).get(id=data["order_id"])
                payment_link = create_payment_link_for_order(
                    order=order,
                    installments=data.get("installments", 1),
                    created_by=request.user,
                )
            else:
                payment_link = create_standalone_payment_link(
                    tenant=request.tenant,
                    amount=data["amount"],
                    description=data.get("description", "Link de pagamento"),
                    customer_name=data["customer_name"],
                    customer_phone=data.get("customer_phone", ""),
                    customer_email=data.get("customer_email", ""),
                    installments=data.get("installments", 1),
                    created_by=request.user,
                )
            
            return Response(PaymentLinkSerializer(payment_link).data, status=status.HTTP_201_CREATED)
        
        except Order.DoesNotExist:
            return Response({"error": "Pedido não encontrado"}, status=status.HTTP_404_NOT_FOUND)
        except PagarmeError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
