"""
Views de Clientes - Flowlog.
"""

import csv
from datetime import timedelta, datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Sum, Count, Max, Q
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone

from apps.orders.models import Customer, Order


def _parse_date(date_str, default=None):
    if not date_str:
        return default
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return default


@login_required
def customer_list(request):
    """Lista de clientes com estatísticas e filtros."""
    tenant = request.tenant
    today = timezone.now().date()
    
    # Filtros
    search = request.GET.get('q', '').strip()
    date_from = _parse_date(request.GET.get('date_from'))
    date_to = _parse_date(request.GET.get('date_to'))
    order_filter = request.GET.get('orders', '')  # 'recurrent', 'single', 'none'
    
    # Base queryset
    customers = Customer.objects.for_tenant(tenant)
    
    # Aplicar filtro de busca
    if search:
        customers = customers.filter(
            Q(name__icontains=search) |
            Q(phone__icontains=search) |
            Q(cpf__icontains=search)
        )
    
    # Filtro por data de cadastro
    if date_from:
        customers = customers.filter(created_at__date__gte=date_from)
    if date_to:
        customers = customers.filter(created_at__date__lte=date_to)
    
    # Anotações
    customers = customers.annotate(
        total_orders=Count('orders'),
        total_value=Sum('orders__total_value'),
        last_order_date=Max('orders__created_at')
    )
    
    # Filtro por tipo de cliente
    if order_filter == 'recurrent':
        customers = customers.filter(total_orders__gt=1)
    elif order_filter == 'single':
        customers = customers.filter(total_orders=1)
    elif order_filter == 'none':
        customers = customers.filter(total_orders=0)
    
    # Ordenação
    sort = request.GET.get('sort', '-total_value')
    if sort in ['name', '-name', 'total_orders', '-total_orders', 'total_value', '-total_value', 'created_at', '-created_at']:
        customers = customers.order_by(sort)
    else:
        customers = customers.order_by('-total_value')
    
    # Estatísticas gerais
    all_customers = Customer.objects.for_tenant(tenant)
    total_customers = all_customers.count()
    start_of_month = today.replace(day=1)
    new_this_month = all_customers.filter(created_at__date__gte=start_of_month).count()
    
    repeat_customers = all_customers.annotate(order_count=Count('orders')).filter(order_count__gt=1).count()
    
    orders_agg = Order.objects.for_tenant(tenant).aggregate(total=Sum('total_value'), count=Count('id'))
    avg_ticket = (orders_agg['total'] or 0) / orders_agg['count'] if orders_agg['count'] else 0
    
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
        'search': search,
        'date_from': date_from,
        'date_to': date_to,
        'order_filter': order_filter,
        'sort': sort,
    })


@login_required
def customer_csv(request):
    """Exporta lista de clientes em CSV."""
    tenant = request.tenant
    
    customers = Customer.objects.for_tenant(tenant).annotate(
        total_orders=Count('orders'),
        total_value=Sum('orders__total_value'),
        last_order_date=Max('orders__created_at')
    ).order_by('-total_value')
    
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="clientes.csv"'
    response.write('\ufeff')  # BOM para Excel
    
    writer = csv.writer(response, delimiter=';')
    writer.writerow(['Nome', 'Telefone', 'CPF', 'Total Pedidos', 'Valor Total', 'Último Pedido', 'Cadastro'])
    
    for c in customers:
        writer.writerow([
            c.name,
            c.phone,
            c.cpf or '',
            c.total_orders,
            str(c.total_value or 0).replace('.', ','),
            c.last_order_date.strftime('%d/%m/%Y') if c.last_order_date else '',
            c.created_at.strftime('%d/%m/%Y'),
        ])
    
    return response


@login_required
def customer_detail(request, customer_id):
    """Detalhes do cliente com histórico de pedidos."""
    customer = get_object_or_404(
        Customer.objects.for_tenant(request.tenant),
        id=customer_id
    )
    
    orders = Order.objects.filter(customer=customer).order_by('-created_at')
    
    total_orders = orders.count()
    total_value = orders.aggregate(total=Sum('total_value'))['total'] or 0
    last_order = orders.first()
    
    avg_ticket = total_value / total_orders if total_orders > 0 else 0
    
    stats = {
        'total_orders': total_orders,
        'total_value': total_value,
        'avg_ticket': avg_ticket,
        'last_order': last_order.created_at if last_order else None,
    }
    
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
        
        phone_normalized = ''.join(filter(str.isdigit, phone))
        
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
    
    return render(request, 'customers/customer_edit.html', {'customer': customer})
