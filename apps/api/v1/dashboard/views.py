"""
Views de Dashboard.
"""

from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.orders.models import Order, OrderStatus, PaymentStatus
from apps.api.permissions import IsTenantUser

from .serializers import DashboardSerializer


class DashboardView(APIView):
    """
    GET /api/v1/dashboard/
    
    Retorna métricas do tenant.
    """
    
    permission_classes = [permissions.IsAuthenticated, IsTenantUser]
    
    def get(self, request):
        tenant = request.tenant
        today = timezone.now().date()
        month_start = today.replace(day=1)
        
        orders = Order.objects.filter(tenant=tenant)
        
        # Métricas
        orders_today = orders.filter(sale_date=today).count()
        orders_pending = orders.filter(order_status=OrderStatus.PENDING).count()
        orders_month = orders.filter(sale_date__gte=month_start).count()
        
        # Receita (apenas pagos, excluindo cancelados)
        paid_filter = orders.filter(
            payment_status=PaymentStatus.PAID
        ).exclude(order_status=OrderStatus.CANCELLED)
        
        revenue_today = paid_filter.filter(
            sale_date=today
        ).aggregate(t=Sum("total_value"))["t"] or Decimal("0")
        
        revenue_month = paid_filter.filter(
            sale_date__gte=month_start
        ).aggregate(t=Sum("total_value"))["t"] or Decimal("0")
        
        # Ticket médio
        paid_count = paid_filter.filter(sale_date__gte=month_start).count()
        ticket_medio = revenue_month / paid_count if paid_count > 0 else Decimal("0")
        
        data = {
            "orders_today": orders_today,
            "orders_pending": orders_pending,
            "orders_month": orders_month,
            "revenue_today": revenue_today,
            "revenue_month": revenue_month,
            "ticket_medio": ticket_medio,
        }
        
        return Response(DashboardSerializer(data).data)
