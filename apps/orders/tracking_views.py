"""
Views públicas de acompanhamento - Flowlog.
Não requer autenticação.
"""

from django.shortcuts import render, get_object_or_404
from django.db.models import Q

from apps.orders.models import Order, Customer


def tracking_search(request):
    """Página de busca de pedido para acompanhamento."""
    orders = None
    search = request.GET.get('q', '').strip()
    error = None
    
    if search:
        # Normaliza a busca (remove formatação)
        search_normalized = "".join(filter(str.isdigit, search))
        
        # Busca por código do pedido OU CPF do cliente
        if search.upper().startswith('PED-'):
            # Busca direta por código
            orders = Order.objects.filter(code__iexact=search).select_related('customer', 'tenant')
        elif len(search_normalized) == 11:
            # Busca por CPF (11 dígitos)
            customers = Customer.objects.filter(cpf_normalized=search_normalized)
            if customers.exists():
                orders = Order.objects.filter(customer__in=customers).select_related('customer', 'tenant').order_by('-created_at')[:10]
            else:
                error = "Nenhum cliente encontrado com este CPF."
        else:
            # Tenta buscar por código mesmo sem PED-
            orders = Order.objects.filter(
                Q(code__icontains=search) |
                Q(customer__cpf_normalized=search_normalized)
            ).select_related('customer', 'tenant')[:10]
        
        if orders is not None and not orders.exists():
            error = "Nenhum pedido encontrado."
            orders = None
    
    return render(request, 'tracking/search.html', {
        'orders': orders,
        'search': search,
        'error': error,
    })


def tracking_detail(request, code):
    """Página de detalhes do pedido para acompanhamento público."""
    order = get_object_or_404(
        Order.objects.select_related('customer', 'tenant'),
        code__iexact=code
    )
    
    return render(request, 'tracking/detail.html', {
        'order': order,
    })
