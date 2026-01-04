"""
Views principais do sistema - Dashboard, Relatórios, Configurações, Perfil.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q, Avg
from django.db.models.functions import TruncDate, TruncMonth
from django.shortcuts import render, redirect
from django.utils import timezone
from datetime import timedelta

from apps.orders.models import Order, Customer, DeliveryStatus, DeliveryType, OrderStatus, PaymentStatus


@login_required
def dashboard(request):
    """Dashboard principal com métricas do negócio."""
    tenant = request.tenant
    today = timezone.now().date()
    start_of_month = today.replace(day=1)
    
    # Base queryset
    orders = Order.objects.for_tenant(tenant)
    customers = Customer.objects.for_tenant(tenant)
    
    # Pedidos do período
    period_orders = orders.filter(created_at__date__gte=start_of_month)
    
    # Estatísticas por tipo de entrega
    def get_type_stats(delivery_type):
        qs = period_orders.filter(delivery_type=delivery_type)
        agg = qs.aggregate(
            count=Count('id'),
            value=Sum('total_value')
        )
        return {
            'count': agg['count'] or 0,
            'value': agg['value'] or 0
        }
    
    motoboy_stats = get_type_stats(DeliveryType.MOTOBOY)
    sedex_stats = get_type_stats(DeliveryType.SEDEX)
    pac_stats = get_type_stats(DeliveryType.PAC)
    pickup_stats = get_type_stats(DeliveryType.PICKUP)
    
    # Estatísticas gerais
    stats = {
        # Totais
        'total_orders': orders.count(),
        'orders_today': orders.filter(created_at__date=today).count(),
        'total_customers': customers.count(),
        
        # Por status de entrega
        'pending_orders': orders.filter(
            delivery_status=DeliveryStatus.PENDING,
            order_status__in=[OrderStatus.PENDING, OrderStatus.CONFIRMED]
        ).count(),
        'ready_pickup_orders': orders.filter(delivery_status=DeliveryStatus.READY_FOR_PICKUP).count(),
        'shipped_orders': orders.filter(delivery_status=DeliveryStatus.SHIPPED).count(),
        'delivered_orders': orders.filter(
            delivery_status__in=[DeliveryStatus.DELIVERED, DeliveryStatus.PICKED_UP]
        ).count(),
        'cancelled_orders': orders.filter(order_status=OrderStatus.CANCELLED).count(),
        
        # Faturamento do mês (pedidos não cancelados)
        'total_revenue': period_orders.exclude(
            order_status=OrderStatus.CANCELLED
        ).aggregate(total=Sum('total_value'))['total'] or 0,
        
        # Por tipo de entrega
        'motoboy_count': motoboy_stats['count'],
        'motoboy_value': motoboy_stats['value'],
        'sedex_count': sedex_stats['count'],
        'sedex_value': sedex_stats['value'],
        'pac_count': pac_stats['count'],
        'pac_value': pac_stats['value'],
        'pickup_count': pickup_stats['count'],
        'pickup_value': pickup_stats['value'],
    }
    
    # Pedidos recentes
    recent_orders = (
        orders
        .select_related('customer')
        .order_by('-created_at')[:8]
    )
    
    # Top clientes
    top_customers = (
        customers
        .annotate(
            total_orders=Count('orders'),
            total_value=Sum('orders__total_value')
        )
        .filter(total_orders__gt=0)
        .order_by('-total_value')[:5]
    )
    
    return render(request, 'dashboard/dashboard.html', {
        'stats': stats,
        'recent_orders': recent_orders,
        'top_customers': top_customers,
    })


@login_required
def reports(request):
    """Página de relatórios."""
    tenant = request.tenant
    today = timezone.now().date()
    
    # Período padrão: últimos 30 dias
    period = request.GET.get('period', '30')
    
    if period == '7':
        start_date = today - timedelta(days=7)
    elif period == '30':
        start_date = today - timedelta(days=30)
    elif period == '90':
        start_date = today - timedelta(days=90)
    elif period == '365':
        start_date = today - timedelta(days=365)
    else:
        start_date = today - timedelta(days=30)
    
    orders = Order.objects.for_tenant(tenant).filter(created_at__date__gte=start_date)
    
    # Resumo geral
    summary = orders.aggregate(
        total_orders=Count('id'),
        total_revenue=Sum('total_value'),
        avg_ticket=Avg('total_value'),
    )
    
    # Por status
    status_data = {
        'pending': orders.filter(delivery_status=DeliveryStatus.PENDING, order_status__in=[OrderStatus.PENDING, OrderStatus.CONFIRMED]).count(),
        'shipped': orders.filter(delivery_status=DeliveryStatus.SHIPPED).count(),
        'delivered': orders.filter(delivery_status__in=[DeliveryStatus.DELIVERED, DeliveryStatus.PICKED_UP]).count(),
        'cancelled': orders.filter(order_status=OrderStatus.CANCELLED).count(),
    }
    
    # Por tipo de entrega com valores
    type_data = []
    for dtype, label in DeliveryType.choices:
        data = orders.filter(delivery_type=dtype).aggregate(
            count=Count('id'),
            value=Sum('total_value')
        )
        type_data.append({
            'type': dtype,
            'label': label,
            'count': data['count'] or 0,
            'value': data['value'] or 0,
        })
    
    # Por pagamento
    payment_data = {
        'paid': orders.filter(payment_status=PaymentStatus.PAID).aggregate(
            count=Count('id'),
            value=Sum('total_value')
        ),
        'pending': orders.filter(payment_status=PaymentStatus.PENDING).aggregate(
            count=Count('id'),
            value=Sum('total_value')
        ),
    }
    
    # Vendas por dia (últimos 14 dias para o gráfico)
    daily_sales = (
        orders
        .filter(created_at__date__gte=today - timedelta(days=14))
        .annotate(date=TruncDate('created_at'))
        .values('date')
        .annotate(
            count=Count('id'),
            value=Sum('total_value')
        )
        .order_by('date')
    )
    
    # Top clientes
    top_customers = (
        Customer.objects.for_tenant(tenant)
        .annotate(
            total_orders=Count('orders', filter=Q(orders__created_at__date__gte=start_date)),
            total_value=Sum('orders__total_value', filter=Q(orders__created_at__date__gte=start_date))
        )
        .filter(total_orders__gt=0)
        .order_by('-total_value')[:10]
    )
    
    return render(request, 'reports/reports.html', {
        'period': period,
        'start_date': start_date,
        'summary': summary,
        'status_data': status_data,
        'type_data': type_data,
        'payment_data': payment_data,
        'daily_sales': list(daily_sales),
        'top_customers': top_customers,
    })


@login_required
def settings(request):
    """Página de configurações do tenant."""
    tenant = request.tenant
    tenant_settings = tenant.settings
    
    if request.method == 'POST':
        # Atualizar configurações
        tenant_settings.whatsapp_enabled = request.POST.get('whatsapp_enabled') == 'on'
        tenant_settings.msg_order_created = request.POST.get('msg_order_created', '')
        tenant_settings.msg_order_shipped = request.POST.get('msg_order_shipped', '')
        tenant_settings.msg_order_delivered = request.POST.get('msg_order_delivered', '')
        tenant_settings.msg_order_ready_for_pickup = request.POST.get('msg_order_ready_for_pickup', '')
        tenant_settings.save()
        
        messages.success(request, 'Configurações salvas com sucesso!')
        return redirect('settings')
    
    return render(request, 'settings/settings.html', {
        'tenant': tenant,
        'tenant_settings': tenant_settings,
    })


@login_required
def profile(request):
    """Página de perfil do usuário."""
    user = request.user
    
    if request.method == 'POST':
        user.first_name = request.POST.get('first_name', '')
        user.last_name = request.POST.get('last_name', '')
        
        # Alterar senha
        new_password = request.POST.get('new_password', '')
        confirm_password = request.POST.get('confirm_password', '')
        
        if new_password:
            if new_password == confirm_password:
                user.set_password(new_password)
                messages.success(request, 'Senha alterada! Faça login novamente.')
            else:
                messages.error(request, 'As senhas não coincidem.')
                return redirect('profile')
        
        user.save()
        messages.success(request, 'Perfil atualizado com sucesso!')
        return redirect('profile')
    
    # Estatísticas do usuário
    user_stats = {
        'total_orders': Order.objects.filter(seller=user).count(),
        'orders_month': Order.objects.filter(
            seller=user,
            created_at__month=timezone.now().month
        ).count(),
        'total_revenue': Order.objects.filter(seller=user).aggregate(
            total=Sum('total_value')
        )['total'] or 0,
    }
    
    return render(request, 'profile/profile.html', {
        'user': user,
        'user_stats': user_stats,
    })
