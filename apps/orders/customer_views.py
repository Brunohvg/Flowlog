"""
Views de Clientes - Flowlog.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Sum, Count, Max
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone

from apps.orders.models import Customer, Order


@login_required
def customer_list(request):
    """Lista de clientes com estatísticas."""
    tenant = request.tenant
    today = timezone.now().date()
    start_of_month = today.replace(day=1)
    
    # Base queryset com anotações
    customers = (
        Customer.objects.for_tenant(tenant)
        .annotate(
            total_orders=Count('orders'),
            total_value=Sum('orders__total_value'),
            last_order_date=Max('orders__created_at')
        )
        .order_by('-total_value')
    )
    
    # Estatísticas gerais
    all_customers = Customer.objects.for_tenant(tenant)
    total_customers = all_customers.count()
    new_this_month = all_customers.filter(created_at__date__gte=start_of_month).count()
    
    # Clientes recorrentes (mais de 1 pedido)
    repeat_customers = all_customers.annotate(
        order_count=Count('orders')
    ).filter(order_count__gt=1).count()
    
    # Ticket médio geral
    orders_agg = Order.objects.for_tenant(tenant).aggregate(
        total=Sum('total_value'),
        count=Count('id')
    )
    avg_ticket = 0
    if orders_agg['count'] and orders_agg['count'] > 0:
        avg_ticket = (orders_agg['total'] or 0) / orders_agg['count']
    
    stats = {
        'total_customers': total_customers,
        'new_this_month': new_this_month,
        'repeat_customers': repeat_customers,
        'avg_ticket': avg_ticket,
    }
    
    # Paginação
    paginator = Paginator(customers, 20)
    page = request.GET.get('page', 1)
    customers = paginator.get_page(page)
    
    return render(request, 'customers/customer_list.html', {
        'customers': customers,
        'stats': stats,
    })


@login_required
def customer_detail(request, customer_id):
    """Detalhes do cliente com histórico de pedidos."""
    customer = get_object_or_404(
        Customer.objects.for_tenant(request.tenant),
        id=customer_id
    )
    
    # Pedidos do cliente
    orders = Order.objects.filter(customer=customer).order_by('-created_at')
    
    # Estatísticas - calcular manualmente para evitar erro de aggregate
    total_orders = orders.count()
    total_value = orders.aggregate(total=Sum('total_value'))['total'] or 0
    last_order = orders.first()
    
    # Ticket médio calculado manualmente
    avg_ticket = 0
    if total_orders > 0:
        avg_ticket = total_value / total_orders
    
    stats = {
        'total_orders': total_orders,
        'total_value': total_value,
        'avg_ticket': avg_ticket,
        'last_order': last_order.created_at if last_order else None,
    }
    
    # Paginação
    paginator = Paginator(orders, 10)
    page = request.GET.get('page', 1)
    orders = paginator.get_page(page)
    
    return render(request, 'customers/customer_detail.html', {
        'customer': customer,
        'orders': orders,
        'stats': stats,
    })


@login_required
def customer_edit(request, customer_id):
    """Edição de cliente."""
    customer = get_object_or_404(
        Customer.objects.for_tenant(request.tenant),
        id=customer_id
    )
    
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        phone = request.POST.get('phone', '').strip()
        cpf = request.POST.get('cpf', '').strip()
        
        if not name or not phone:
            messages.error(request, 'Nome e telefone são obrigatórios.')
            return redirect('customer_edit', customer_id=customer_id)
        
        # Normalizar telefone
        phone_normalized = ''.join(filter(str.isdigit, phone))
        
        # Verificar duplicidade (exceto o próprio cliente)
        existing = Customer.objects.for_tenant(request.tenant).filter(
            phone_normalized=phone_normalized
        ).exclude(id=customer.id).first()
        
        if existing:
            messages.error(request, f'Já existe um cliente com este telefone: {existing.name}')
            return redirect('customer_edit', customer_id=customer_id)
        
        customer.name = name
        customer.phone = phone
        customer.phone_normalized = phone_normalized
        customer.cpf = cpf
        customer.save()
        
        messages.success(request, 'Cliente atualizado com sucesso!')
        return redirect('customer_detail', customer_id=customer_id)
    
    return render(request, 'customers/customer_edit.html', {
        'customer': customer,
    })
