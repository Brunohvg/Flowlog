"""
Views do app orders - Flowlog.
Views são burras. Apenas buscam dados e delegam para services.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.orders.forms import OrderCancelForm, OrderCreateForm, OrderShipForm
from apps.orders.models import Order, DeliveryStatus, DeliveryType, OrderStatus, PaymentStatus
from apps.orders.services import OrderService, OrderStatusService


@login_required
def order_list(request):
    """Lista de pedidos com filtros e paginação."""
    orders = (
        Order.objects.for_tenant(request.tenant)
        .select_related("customer", "seller")
        .order_by("-created_at")
    )
    
    # Filtros
    search = request.GET.get('q', '')
    status = request.GET.get('status', '')
    delivery_type = request.GET.get('type', '')
    payment = request.GET.get('payment', '')
    priority = request.GET.get('priority', '')
    
    if search:
        orders = orders.filter(
            Q(code__icontains=search) |
            Q(customer__name__icontains=search) |
            Q(customer__phone__icontains=search) |
            Q(pickup_code__icontains=search)  # Busca por código de retirada
        )
    
    if status:
        if status == 'pending':
            orders = orders.filter(
                delivery_status=DeliveryStatus.PENDING,
                order_status__in=[OrderStatus.PENDING, OrderStatus.CONFIRMED]
            )
        elif status == 'shipped':
            orders = orders.filter(delivery_status__in=[DeliveryStatus.SHIPPED, DeliveryStatus.FAILED_ATTEMPT])
        elif status == 'delivered':
            orders = orders.filter(
                delivery_status__in=[DeliveryStatus.DELIVERED, DeliveryStatus.PICKED_UP]
            )
        elif status == 'cancelled':
            orders = orders.filter(order_status__in=[OrderStatus.CANCELLED, OrderStatus.RETURNED])
        elif status == 'ready' or status == 'ready_pickup':
            orders = orders.filter(delivery_status=DeliveryStatus.READY_FOR_PICKUP)
    
    if delivery_type:
        orders = orders.filter(delivery_type=delivery_type)
    
    if payment:
        if payment == 'paid':
            orders = orders.filter(payment_status=PaymentStatus.PAID)
        elif payment == 'pending':
            orders = orders.filter(payment_status=PaymentStatus.PENDING)
    
    if priority == '1':
        orders = orders.filter(is_priority=True)
    
    # Paginação
    paginator = Paginator(orders, 20)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    return render(request, "orders/order_list.html", {
        "page_obj": page_obj,
    })


@login_required
def order_create(request):
    """Criação de pedido."""
    if request.method == "POST":
        form = OrderCreateForm(request.POST)
        if form.is_valid():
            try:
                order = OrderService().create_order(
                    tenant=request.tenant,
                    seller=request.user,
                    data=form.cleaned_data,
                )
                messages.success(request, f"Pedido {order.code} criado com sucesso!")
                return redirect("order_detail", order_id=order.id)
            except ValueError as e:
                messages.error(request, str(e))
    else:
        form = OrderCreateForm()
    
    return render(request, "orders/order_create.html", {"form": form})


@login_required
def order_detail(request, order_id):
    """Detalhes do pedido com histórico de atividades."""
    order = get_object_or_404(
        Order.objects.for_tenant(request.tenant)
        .select_related("customer", "seller")
        .prefetch_related("activities"),
        id=order_id,
    )
    
    # Últimas 20 atividades
    activities = order.activities.select_related("user").order_by("-created_at")[:20]
    
    return render(request, "orders/order_detail.html", {
        "order": order,
        "activities": activities,
    })


@login_required
def order_edit(request, order_id):
    """Edição de pedido."""
    order = get_object_or_404(
        Order.objects.for_tenant(request.tenant).select_related("customer"),
        id=order_id,
    )
    
    # Não permite editar pedidos finalizados
    if order.order_status in [OrderStatus.COMPLETED, OrderStatus.CANCELLED, OrderStatus.RETURNED]:
        messages.error(request, "Este pedido não pode ser editado.")
        return redirect("order_detail", order_id=order_id)
    
    if request.method == "POST":
        total_value = request.POST.get("total_value", "").replace(".", "").replace(",", ".")
        delivery_address = request.POST.get("delivery_address", "").strip()
        notes = request.POST.get("notes", "").strip()
        internal_notes = request.POST.get("internal_notes", "").strip()
        is_priority = request.POST.get("is_priority") == "on"
        
        # Campos motoboy
        motoboy_fee = request.POST.get("motoboy_fee", "").replace(".", "").replace(",", ".")
        motoboy_paid = request.POST.get("motoboy_paid") == "on"
        
        try:
            from decimal import Decimal, ROUND_HALF_UP
            if total_value:
                order.total_value = Decimal(total_value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            order.delivery_address = delivery_address
            order.notes = notes
            order.internal_notes = internal_notes
            order.is_priority = is_priority
            
            # Salvar campos motoboy (só se for entrega motoboy)
            if order.delivery_type == 'motoboy':
                if motoboy_fee:
                    order.motoboy_fee = Decimal(motoboy_fee).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                else:
                    order.motoboy_fee = None
                order.motoboy_paid = motoboy_paid
            
            order.save()
            
            from apps.orders.models import OrderActivity
            OrderActivity.log(
                order=order,
                activity_type=OrderActivity.ActivityType.EDITED,
                description="Pedido editado",
                user=request.user,
            )
            
            messages.success(request, f"Pedido {order.code} atualizado!")
            return redirect("order_detail", order_id=order_id)
        except (ValueError, TypeError):
            messages.error(request, "Valor inválido.")
    
    return render(request, "orders/order_edit.html", {"order": order})


@login_required
def order_mark_paid(request, order_id):
    """Marca pedido como pago."""
    order = get_object_or_404(
        Order.objects.for_tenant(request.tenant), id=order_id
    )
    
    try:
        OrderStatusService().mark_as_paid(order=order, actor=request.user)
        messages.success(request, f"Pedido {order.code} marcado como pago!")
    except ValueError as e:
        messages.error(request, str(e))
    
    return redirect("order_detail", order_id=order_id)


@login_required
def order_mark_shipped(request, order_id):
    """Marca pedido como enviado."""
    order = get_object_or_404(
        Order.objects.for_tenant(request.tenant), id=order_id
    )
    
    if request.method == "POST":
        form = OrderShipForm(request.POST, order=order)
        if form.is_valid():
            try:
                OrderStatusService().mark_as_shipped(
                    order=order,
                    actor=request.user,
                    tracking_code=form.cleaned_data.get("tracking_code"),
                )
                messages.success(request, f"Pedido {order.code} marcado como enviado!")
                return redirect("order_detail", order_id=order_id)
            except ValueError as e:
                messages.error(request, str(e))
    else:
        form = OrderShipForm(order=order)
    
    return render(request, "orders/order_ship.html", {"order": order, "form": form})


@login_required
def order_mark_delivered(request, order_id):
    """Marca pedido como entregue."""
    order = get_object_or_404(
        Order.objects.for_tenant(request.tenant), id=order_id
    )
    
    try:
        OrderStatusService().mark_as_delivered(order=order, actor=request.user)
        messages.success(request, f"Pedido {order.code} marcado como entregue!")
    except ValueError as e:
        messages.error(request, str(e))
    
    return redirect("order_detail", order_id=order_id)


@login_required
def order_mark_failed_attempt(request, order_id):
    """Marca tentativa de entrega falha."""
    order = get_object_or_404(
        Order.objects.for_tenant(request.tenant), id=order_id
    )
    
    reason = request.POST.get("reason", "") if request.method == "POST" else ""
    
    try:
        OrderStatusService().mark_failed_attempt(order=order, actor=request.user, reason=reason)
        messages.warning(request, f"Tentativa de entrega registrada para {order.code}")
    except ValueError as e:
        messages.error(request, str(e))
    
    return redirect("order_detail", order_id=order_id)


@login_required
def order_ready_for_pickup(request, order_id):
    """Marca pedido como pronto para retirada."""
    order = get_object_or_404(
        Order.objects.for_tenant(request.tenant), id=order_id
    )
    
    try:
        OrderStatusService().mark_ready_for_pickup(order=order, actor=request.user)
        messages.success(request, f"Pedido {order.code} pronto para retirada!")
    except ValueError as e:
        messages.error(request, str(e))
    
    return redirect("order_detail", order_id=order_id)


@login_required
def order_mark_picked_up(request, order_id):
    """Marca pedido como retirado."""
    order = get_object_or_404(
        Order.objects.for_tenant(request.tenant), id=order_id
    )
    
    try:
        OrderStatusService().mark_as_picked_up(order=order, actor=request.user)
        messages.success(request, f"Pedido {order.code} retirado pelo cliente!")
    except ValueError as e:
        messages.error(request, str(e))
    
    return redirect("order_detail", order_id=order_id)


@login_required
def order_cancel(request, order_id):
    """Cancela pedido."""
    order = get_object_or_404(
        Order.objects.for_tenant(request.tenant).select_related("customer"),
        id=order_id,
    )
    
    if request.method == "POST":
        form = OrderCancelForm(request.POST)
        if form.is_valid():
            try:
                OrderStatusService().cancel_order(
                    order=order,
                    actor=request.user,
                    reason=form.cleaned_data.get("reason", ""),
                )
                messages.success(request, f"Pedido {order.code} cancelado.")
                return redirect("order_list")
            except ValueError as e:
                messages.error(request, str(e))
    else:
        form = OrderCancelForm()
    
    return render(request, "orders/order_cancel.html", {"order": order, "form": form})


@login_required
def order_delete(request, order_id):
    """Deleta pedido permanentemente."""
    order = get_object_or_404(
        Order.objects.for_tenant(request.tenant),
        id=order_id,
    )
    
    if request.method == "POST":
        try:
            code = OrderStatusService().delete_order(order=order, actor=request.user)
            messages.success(request, f"Pedido {code} deletado.")
            return redirect("order_list")
        except ValueError as e:
            messages.error(request, str(e))
            return redirect("order_detail", order_id=order_id)
    
    return redirect("order_detail", order_id=order_id)


@login_required
def order_return(request, order_id):
    """Processa devolução de pedido."""
    order = get_object_or_404(
        Order.objects.for_tenant(request.tenant).select_related("customer"),
        id=order_id,
    )
    
    if request.method == "POST":
        reason = request.POST.get("reason", "")
        refund = request.POST.get("refund") == "on"
        
        try:
            OrderStatusService().return_order(
                order=order,
                actor=request.user,
                reason=reason,
                refund=refund,
            )
            messages.success(request, f"Devolução do pedido {order.code} processada.")
            return redirect("order_detail", order_id=order_id)
        except ValueError as e:
            messages.error(request, str(e))
    
    return render(request, "orders/order_return.html", {"order": order})


@login_required
def order_change_delivery(request, order_id):
    """Altera tipo de entrega do pedido."""
    order = get_object_or_404(
        Order.objects.for_tenant(request.tenant).select_related("customer"),
        id=order_id,
    )
    
    if request.method == "POST":
        new_type = request.POST.get("delivery_type", "")
        address = request.POST.get("delivery_address", "")
        
        try:
            OrderStatusService().change_delivery_type(
                order=order,
                actor=request.user,
                new_type=new_type,
                address=address,
            )
            messages.success(request, f"Tipo de entrega do pedido {order.code} alterado.")
            return redirect("order_detail", order_id=order_id)
        except ValueError as e:
            messages.error(request, str(e))
    
    return render(request, "orders/order_change_delivery.html", {"order": order})


@login_required
def order_duplicate(request, order_id):
    """Duplica um pedido."""
    order = get_object_or_404(
        Order.objects.for_tenant(request.tenant).select_related("customer"),
        id=order_id,
    )
    
    try:
        new_order = OrderService().duplicate_order(order=order, actor=request.user)
        messages.success(request, f"Pedido duplicado! Novo código: {new_order.code}")
        return redirect("order_detail", order_id=new_order.id)
    except ValueError as e:
        messages.error(request, str(e))
        return redirect("order_detail", order_id=order_id)


@login_required
def order_resend_notification(request, order_id):
    """Reenvia notificação WhatsApp."""
    order = get_object_or_404(
        Order.objects.for_tenant(request.tenant),
        id=order_id,
    )
    
    notification_type = request.POST.get("type", "created") if request.method == "POST" else "created"
    
    try:
        OrderStatusService().resend_notification(order=order, notification_type=notification_type)
        messages.success(request, f"Notificação reenviada para {order.customer.phone}!")
    except ValueError as e:
        messages.error(request, str(e))
    
    return redirect("order_detail", order_id=order_id)


@login_required
def order_label(request, order_id):
    """Etiqueta de impressão do pedido."""
    order = get_object_or_404(
        Order.objects.for_tenant(request.tenant).select_related("customer"),
        id=order_id,
    )

    return render(request, "orders/order_label.html", {"order": order})


# ==============================================================================
# API: Validação de Código de Retirada
# ==============================================================================

from django.http import JsonResponse
from django.urls import reverse

@login_required
def validate_pickup_code(request):
    """
    API para validar código de retirada.
    Usado pelo scanner/input na lista de pedidos.
    
    GET /pedidos/validar-retirada/?code=1234
    
    Retorna JSON:
    - found: true/false
    - order: {code, customer, value, detail_url, pickup_url}
    - message: mensagem de erro se não encontrado
    """
    code = request.GET.get('code', '').strip()
    
    if not code or len(code) != 4:
        return JsonResponse({
            'found': False,
            'message': 'Código deve ter 4 dígitos'
        })
    
    # Busca pedido pelo código de retirada
    order = Order.objects.filter(
        tenant=request.tenant,
        pickup_code=code,
        delivery_status=DeliveryStatus.READY_FOR_PICKUP
    ).select_related('customer').first()
    
    if not order:
        # Verifica se existe mas já foi retirado
        picked_up = Order.objects.filter(
            tenant=request.tenant,
            pickup_code=code,
            delivery_status=DeliveryStatus.PICKED_UP
        ).exists()
        
        if picked_up:
            return JsonResponse({
                'found': False,
                'message': 'Este pedido já foi retirado'
            })
        
        return JsonResponse({
            'found': False,
            'message': 'Código não encontrado'
        })
    
    # Verifica se expirou
    if order.is_expired:
        return JsonResponse({
            'found': False,
            'message': f'Pedido {order.code} expirou'
        })
    
    return JsonResponse({
        'found': True,
        'order': {
            'id': str(order.id),
            'code': order.code,
            'customer': order.customer.name,
            'phone': order.customer.phone,
            'value': f"{order.total_value:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            'payment_status': order.get_payment_status_display(),
            'detail_url': reverse('order_detail', args=[order.id]),
            'pickup_url': reverse('order_mark_picked_up', args=[order.id]),
        }
    })


@login_required
def quick_pickup(request, order_id):
    """
    Marca pedido como retirado via AJAX (para uso no validador rápido).
    
    POST /pedidos/{id}/retirada-rapida/
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Método não permitido'}, status=405)
    
    order = get_object_or_404(
        Order.objects.for_tenant(request.tenant),
        id=order_id,
    )
    
    try:
        OrderStatusService().mark_as_picked_up(order=order, actor=request.user)
        return JsonResponse({
            'success': True,
            'message': f'Pedido {order.code} marcado como retirado!'
        })
    except ValueError as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)
