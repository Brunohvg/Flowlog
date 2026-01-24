"""
Views da API v1 - Flowlog

Endpoints:
- /api/v1/customers/ - CRUD de clientes
- /api/v1/orders/ - CRUD de pedidos
- /api/v1/orders/{id}/status/ - Atualizar status
- /api/v1/payment-links/ - Links de pagamento
- /api/v1/dashboard/ - Estatísticas
"""

from decimal import Decimal

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.orders.models import Customer, Order, OrderStatus, PaymentStatus
from apps.orders.services import OrderService, OrderStatusService
from apps.payments.models import PaymentLink
from apps.payments.services import (
    PagarmeError,
    create_payment_link_for_order,
    create_standalone_payment_link,
)

from .serializers import (
    CustomerCreateSerializer,
    CustomerListSerializer,
    CustomerSerializer,
    DashboardStatsSerializer,
    OrderCreateSerializer,
    OrderListSerializer,
    OrderSerializer,
    OrderStatusUpdateSerializer,
    PaymentLinkCreateSerializer,
    PaymentLinkSerializer,
)

# ==============================================================================
# MIXINS
# ==============================================================================


class TenantMixin:
    """Mixin para filtrar por tenant"""

    def get_queryset(self):
        qs = super().get_queryset()
        if hasattr(self.request, "tenant"):
            return qs.filter(tenant=self.request.tenant)
        return qs.none()


# ==============================================================================
# CUSTOMER
# ==============================================================================


class CustomerViewSet(TenantMixin, viewsets.ModelViewSet):
    """
    API de Clientes

    list: Lista todos os clientes
    retrieve: Busca cliente por ID
    create: Cria novo cliente
    update: Atualiza cliente
    partial_update: Atualiza parcialmente
    destroy: Remove cliente
    """

    queryset = Customer.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action == "list":
            return CustomerListSerializer
        if self.action == "create":
            return CustomerCreateSerializer
        return CustomerSerializer

    def get_queryset(self):
        qs = super().get_queryset()

        # Filtros
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(
                Q(name__icontains=search)
                | Q(phone__icontains=search)
                | Q(email__icontains=search)
            )

        return qs.order_by("-created_at")

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.tenant)


# ==============================================================================
# ORDER
# ==============================================================================


class OrderViewSet(TenantMixin, viewsets.ModelViewSet):
    """
    API de Pedidos

    list: Lista pedidos (com filtros)
    retrieve: Busca pedido por ID
    create: Cria novo pedido
    update: Atualiza pedido
    destroy: Remove pedido

    Actions:
    - status: Atualiza status do pedido
    - payment-link: Cria link de pagamento
    """

    queryset = Order.objects.select_related("customer", "seller")
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action == "list":
            return OrderListSerializer
        if self.action == "create":
            return OrderCreateSerializer
        if self.action == "status":
            return OrderStatusUpdateSerializer
        return OrderSerializer

    def get_queryset(self):
        qs = super().get_queryset()

        # Filtros
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(order_status=status_filter)

        payment_filter = self.request.query_params.get("payment")
        if payment_filter:
            qs = qs.filter(payment_status=payment_filter)

        delivery_filter = self.request.query_params.get("delivery")
        if delivery_filter:
            qs = qs.filter(delivery_status=delivery_filter)

        date_from = self.request.query_params.get("date_from")
        if date_from:
            qs = qs.filter(sale_date__gte=date_from)

        date_to = self.request.query_params.get("date_to")
        if date_to:
            qs = qs.filter(sale_date__lte=date_to)

        return qs.order_by("-created_at")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        # Usa o OrderService para criar
        service = OrderService()

        try:
            order = service.create_order(
                tenant=request.tenant,
                seller=request.user,
                data={
                    "customer_id": str(data.get("customer_id"))
                    if data.get("customer_id")
                    else None,
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

    @action(detail=True, methods=["patch"])
    def status(self, request, pk=None):
        """Atualiza status do pedido"""
        order = self.get_object()
        serializer = OrderStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        service = OrderStatusService()
        actor = request.user

        try:
            # Transições disparadas via Service para garantir side-effects (Logs, WhatsApp)
            if data.get("order_status") == OrderStatus.CANCELLED:
                order = service.cancel_order(
                    order=order, actor=actor, reason=data.get("cancel_reason", "")
                )
            elif data.get("order_status") == OrderStatus.RETURNED:
                order = service.return_order(
                    order=order, actor=actor, reason=data.get("return_reason", "")
                )

            if data.get("payment_status") == PaymentStatus.PAID:
                order = service.mark_as_paid(order=order, actor=actor)

            if data.get("delivery_status") == DeliveryStatus.SHIPPED:
                order = service.mark_as_shipped(
                    order=order, actor=actor, tracking_code=data.get("tracking_code")
                )
            elif data.get("delivery_status") == DeliveryStatus.DELIVERED:
                order = service.mark_as_delivered(order=order, actor=actor)
            elif data.get("delivery_status") == DeliveryStatus.READY_FOR_PICKUP:
                order = service.mark_ready_for_pickup(order=order, actor=actor)
            elif data.get("delivery_status") == DeliveryStatus.PICKED_UP:
                order = service.mark_as_picked_up(order=order, actor=actor)
            elif data.get("delivery_status") == DeliveryStatus.FAILED_ATTEMPT:
                order = service.mark_failed_attempt(
                    order=order, actor=actor, reason="Tentativa via API"
                )

            # Se nenhum status de fluxo principal mudou, mas forneceu tracking code
            if (
                "tracking_code" in data
                and order.delivery_status == DeliveryStatus.SHIPPED
                and data["tracking_code"] != order.tracking_code
            ):
                order.tracking_code = data["tracking_code"]
                order.save(update_fields=["tracking_code", "updated_at"])

        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(OrderSerializer(order).data)

    @action(detail=True, methods=["post"], url_path="payment-link")
    def payment_link(self, request, pk=None):
        """Cria link de pagamento para o pedido"""
        order = self.get_object()

        installments = int(request.data.get("installments", 1))

        try:
            payment_link = create_payment_link_for_order(
                order=order,
                installments=installments,
                created_by=request.user,
            )

            # DISPARO DE NOTIFICAÇÃO (Adicionado para consistência com Interface Web)
            from apps.integrations.whatsapp.tasks import send_payment_link_whatsapp

            transaction.on_commit(
                lambda: send_payment_link_whatsapp.apply_async(
                    args=[str(order.id), str(payment_link.id)],
                    expires=300,
                    ignore_result=True,
                )
            )

            return Response(
                PaymentLinkSerializer(payment_link).data, status=status.HTTP_201_CREATED
            )

        except PagarmeError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


# ==============================================================================
# PAYMENT LINK
# ==============================================================================


class PaymentLinkViewSet(TenantMixin, viewsets.ModelViewSet):
    """
    API de Links de Pagamento

    list: Lista todos os links
    retrieve: Busca link por ID
    create: Cria link avulso ou para pedido
    """

    queryset = PaymentLink.objects.select_related("order")
    serializer_class = PaymentLinkSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]

    def get_serializer_class(self):
        if self.action == "create":
            return PaymentLinkCreateSerializer
        return PaymentLinkSerializer

    def get_queryset(self):
        qs = super().get_queryset()

        # Filtros
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
                # Link para pedido existente
                order = Order.objects.for_tenant(request.tenant).get(
                    id=data["order_id"]
                )
                payment_link = create_payment_link_for_order(
                    order=order,
                    installments=data.get("installments", 1),
                    created_by=request.user,
                )
            else:
                # Link avulso
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

            return Response(
                PaymentLinkSerializer(payment_link).data, status=status.HTTP_201_CREATED
            )

        except Order.DoesNotExist:
            return Response(
                {"error": "Pedido não encontrado"}, status=status.HTTP_404_NOT_FOUND
            )
        except PagarmeError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


# ==============================================================================
# DASHBOARD
# ==============================================================================


class DashboardView(APIView):
    """
    Estatísticas do Dashboard

    GET /api/v1/dashboard/
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        tenant = request.tenant
        today = timezone.now().date()
        month_start = today.replace(day=1)

        # Queries
        orders_qs = Order.objects.filter(tenant=tenant)

        # Métricas
        orders_today = orders_qs.filter(sale_date=today).count()
        orders_pending = orders_qs.filter(order_status=OrderStatus.PENDING).count()
        orders_month = orders_qs.filter(sale_date__gte=month_start).count()

        revenue_today = orders_qs.filter(
            sale_date=today,
            payment_status=PaymentStatus.PAID,
        ).exclude(order_status=OrderStatus.CANCELLED).aggregate(
            total=Sum("total_value")
        )["total"] or Decimal("0")

        revenue_month = orders_qs.filter(
            sale_date__gte=month_start,
            payment_status=PaymentStatus.PAID,
        ).exclude(order_status=OrderStatus.CANCELLED).aggregate(
            total=Sum("total_value")
        )["total"] or Decimal("0")

        # Ticket médio
        paid_orders = (
            orders_qs.filter(
                sale_date__gte=month_start,
                payment_status=PaymentStatus.PAID,
            )
            .exclude(order_status=OrderStatus.CANCELLED)
            .count()
        )

        ticket_medio = revenue_month / paid_orders if paid_orders > 0 else Decimal("0")

        data = {
            "orders_today": orders_today,
            "orders_pending": orders_pending,
            "orders_month": orders_month,
            "revenue_today": revenue_today,
            "revenue_month": revenue_month,
            "ticket_medio": ticket_medio,
        }

        serializer = DashboardStatsSerializer(data)
        return Response(serializer.data)
