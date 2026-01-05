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
    now = timezone.now()
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
        'failed_attempt_orders': orders.filter(delivery_status=DeliveryStatus.FAILED_ATTEMPT).count(),
        'delivered_orders': orders.filter(
            delivery_status__in=[DeliveryStatus.DELIVERED, DeliveryStatus.PICKED_UP]
        ).count(),
        'cancelled_orders': orders.filter(order_status=OrderStatus.CANCELLED).count(),
        
        # Faturamento do mês (pedidos não cancelados)
        'total_revenue': period_orders.exclude(
            order_status__in=[OrderStatus.CANCELLED, OrderStatus.RETURNED]
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
        
        # Pagamentos pendentes
        'pending_payments': orders.filter(
            payment_status=PaymentStatus.PENDING,
            order_status__in=[OrderStatus.PENDING, OrderStatus.CONFIRMED]
        ).count(),
        'pending_payments_value': orders.filter(
            payment_status=PaymentStatus.PENDING,
            order_status__in=[OrderStatus.PENDING, OrderStatus.CONFIRMED]
        ).aggregate(total=Sum('total_value'))['total'] or 0,
        
        # Pedidos prioritários pendentes
        'priority_orders': orders.filter(
            is_priority=True,
            order_status__in=[OrderStatus.PENDING, OrderStatus.CONFIRMED],
            delivery_status__in=[DeliveryStatus.PENDING, DeliveryStatus.READY_FOR_PICKUP]
        ).count(),
    }
    
    # ALERTAS
    alerts = []
    
    # Pedidos de retirada prestes a expirar (menos de 12h)
    expiring_soon = orders.filter(
        delivery_status=DeliveryStatus.READY_FOR_PICKUP,
        expires_at__isnull=False,
        expires_at__lte=now + timedelta(hours=12),
        expires_at__gt=now
    ).count()
    if expiring_soon:
        alerts.append({
            'type': 'warning',
            'icon': 'clock',
            'message': f'{expiring_soon} pedido(s) de retirada expira(m) em menos de 12h',
            'url': '?status=ready'
        })
    
    # Pedidos com tentativa de entrega falha
    failed_attempts = stats['failed_attempt_orders']
    if failed_attempts:
        alerts.append({
            'type': 'error',
            'icon': 'alert-triangle',
            'message': f'{failed_attempts} pedido(s) com tentativa de entrega falha',
            'url': '?status=shipped'
        })
    
    # Pedidos prioritários pendentes
    if stats['priority_orders']:
        alerts.append({
            'type': 'info',
            'icon': 'alert-circle',
            'message': f'{stats["priority_orders"]} pedido(s) prioritário(s) aguardando',
            'url': '?priority=1'
        })
    
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
        'alerts': alerts,
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
        action = request.POST.get('action', 'save_messages')
        
        if action == 'save_whatsapp':
            # Configurações da Evolution API
            tenant_settings.whatsapp_enabled = request.POST.get('whatsapp_enabled') == 'on'
            tenant_settings.evolution_api_url = request.POST.get('evolution_api_url', '').strip()
            tenant_settings.evolution_api_key = request.POST.get('evolution_api_key', '').strip()
            tenant_settings.evolution_instance = request.POST.get('evolution_instance', '').strip()
            tenant_settings.save()
            messages.success(request, 'Configurações do WhatsApp salvas!')
            
        elif action == 'save_messages':
            # Mensagens customizáveis
            tenant_settings.msg_order_created = request.POST.get('msg_order_created', '')
            tenant_settings.msg_order_confirmed = request.POST.get('msg_order_confirmed', '')
            tenant_settings.msg_payment_received = request.POST.get('msg_payment_received', '')
            tenant_settings.msg_payment_refunded = request.POST.get('msg_payment_refunded', '')
            tenant_settings.msg_order_shipped = request.POST.get('msg_order_shipped', '')
            tenant_settings.msg_order_delivered = request.POST.get('msg_order_delivered', '')
            tenant_settings.msg_delivery_failed = request.POST.get('msg_delivery_failed', '')
            tenant_settings.msg_order_ready_for_pickup = request.POST.get('msg_order_ready_for_pickup', '')
            tenant_settings.msg_order_picked_up = request.POST.get('msg_order_picked_up', '')
            tenant_settings.msg_order_expired = request.POST.get('msg_order_expired', '')
            tenant_settings.msg_order_cancelled = request.POST.get('msg_order_cancelled', '')
            tenant_settings.msg_order_returned = request.POST.get('msg_order_returned', '')
            tenant_settings.save()
            messages.success(request, 'Mensagens salvas com sucesso!')
            
        elif action == 'save_store':
            # Informações da loja
            tenant.name = request.POST.get('store_name', tenant.name)
            tenant.contact_email = request.POST.get('contact_email', tenant.contact_email)
            tenant.contact_phone = request.POST.get('contact_phone', '')
            tenant.address = request.POST.get('address', '')
            tenant.save()
            messages.success(request, 'Informações da loja salvas!')
            
        elif action == 'test_whatsapp':
            # Testar conexão com WhatsApp
            if tenant_settings.is_whatsapp_configured:
                try:
                    from apps.integrations.whatsapp.client import EvolutionClient
                    client = EvolutionClient(
                        base_url=tenant_settings.evolution_api_url,
                        api_key=tenant_settings.evolution_api_key,
                        instance=tenant_settings.evolution_instance,
                    )
                    status = client.get_instance_status()
                    if status.get('connected'):
                        tenant_settings.whatsapp_connected = True
                        tenant_settings.whatsapp_number = status.get('number', '')
                        tenant_settings.save()
                        messages.success(request, f'WhatsApp conectado! Número: {tenant_settings.whatsapp_number}')
                    else:
                        tenant_settings.whatsapp_connected = False
                        tenant_settings.save()
                        messages.warning(request, 'Instância encontrada mas não conectada. Escaneie o QR Code.')
                except Exception as e:
                    messages.error(request, f'Erro ao conectar: {str(e)}')
            else:
                messages.error(request, 'Configure a API antes de testar.')
        
        return redirect('settings')
    
    # Placeholders disponíveis para referência
    placeholders = {
        'geral': ['nome', 'codigo', 'valor', 'loja', 'link_rastreio'],
        'entrega': ['rastreio', 'rastreio_info'],
        'retirada': ['endereco'],
        'tentativa': ['tentativa'],
        'cancelamento': ['motivo', 'motivo_info'],
    }
    
    return render(request, 'settings/settings.html', {
        'tenant': tenant,
        'tenant_settings': tenant_settings,
        'placeholders': placeholders,
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
