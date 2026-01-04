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
    
    if search:
        orders = orders.filter(
            Q(code__icontains=search) |
            Q(customer__name__icontains=search) |
            Q(customer__phone__icontains=search)
        )
    
    if status:
        if status == 'pending':
            orders = orders.filter(
                delivery_status=DeliveryStatus.PENDING,
                order_status__in=[OrderStatus.PENDING, OrderStatus.CONFIRMED]
            )
        elif status == 'shipped':
            orders = orders.filter(delivery_status=DeliveryStatus.SHIPPED)
        elif status == 'delivered':
            orders = orders.filter(
                delivery_status__in=[DeliveryStatus.DELIVERED, DeliveryStatus.PICKED_UP]
            )
        elif status == 'cancelled':
            orders = orders.filter(order_status=OrderStatus.CANCELLED)
    
    if delivery_type:
        orders = orders.filter(delivery_type=delivery_type)
    
    if payment:
        if payment == 'paid':
            orders = orders.filter(payment_status=PaymentStatus.PAID)
        elif payment == 'pending':
            orders = orders.filter(payment_status=PaymentStatus.PENDING)
    
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
                return redirect("order_list")
            except ValueError as e:
                messages.error(request, str(e))
        else:
            for error in form.non_field_errors():
                messages.error(request, error)
    else:
        form = OrderCreateForm()

    return render(request, "orders/order_create.html", {"form": form})


@login_required
def order_detail(request, order_id):
    """Detalhe do pedido."""
    order = get_object_or_404(
        Order.objects.for_tenant(request.tenant).select_related("customer", "seller"),
        id=order_id,
    )

    return render(request, "orders/order_detail.html", {"order": order})


@login_required
def order_mark_shipped(request, order_id):
    """Marca pedido como enviado."""
    order = get_object_or_404(
        Order.objects.for_tenant(request.tenant),
        id=order_id,
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
                return redirect("order_list")
            except ValueError as e:
                messages.error(request, str(e))
    else:
        form = OrderShipForm(order=order)

    # Se precisa de rastreio ou é Correios, mostra formulário
    if order.requires_tracking or order.is_correios:
        return render(request, "orders/order_ship.html", {
            "order": order,
            "form": form,
        })

    # Motoboy: envia direto
    try:
        OrderStatusService().mark_as_shipped(
            order=order,
            actor=request.user,
        )
        messages.success(request, f"Pedido {order.code} marcado como enviado!")
    except ValueError as e:
        messages.error(request, str(e))

    return redirect("order_list")


@login_required
def order_mark_delivered(request, order_id):
    """Marca pedido como entregue."""
    order = get_object_or_404(
        Order.objects.for_tenant(request.tenant),
        id=order_id,
    )

    try:
        OrderStatusService().mark_as_delivered(
            order=order,
            actor=request.user,
        )
        messages.success(request, f"Pedido {order.code} marcado como entregue!")
    except ValueError as e:
        messages.error(request, str(e))

    return redirect("order_list")


@login_required
def order_ready_for_pickup(request, order_id):
    """Marca pedido como pronto para retirada."""
    order = get_object_or_404(
        Order.objects.for_tenant(request.tenant),
        id=order_id,
    )

    try:
        OrderStatusService().mark_ready_for_pickup(
            order=order,
            actor=request.user,
        )
        messages.success(request, f"Pedido {order.code} liberado para retirada!")
    except ValueError as e:
        messages.error(request, str(e))

    return redirect("order_list")


@login_required
def order_mark_picked_up(request, order_id):
    """Marca pedido como retirado pelo cliente."""
    order = get_object_or_404(
        Order.objects.for_tenant(request.tenant),
        id=order_id,
    )

    try:
        OrderStatusService().mark_as_picked_up(
            order=order,
            actor=request.user,
        )
        messages.success(request, f"Pedido {order.code} marcado como retirado!")
    except ValueError as e:
        messages.error(request, str(e))

    return redirect("order_list")


@login_required
def order_cancel(request, order_id):
    """Cancela um pedido."""
    order = get_object_or_404(
        Order.objects.for_tenant(request.tenant),
        id=order_id,
    )

    if request.method == "POST":
        form = OrderCancelForm(request.POST)
        if form.is_valid():
            try:
                OrderStatusService().cancel_order(
                    order=order,
                    actor=request.user,
                    reason=form.cleaned_data.get("reason"),
                )
                messages.success(request, f"Pedido {order.code} cancelado!")
                return redirect("order_list")
            except ValueError as e:
                messages.error(request, str(e))
    else:
        form = OrderCancelForm()

    return render(request, "orders/order_cancel.html", {
        "order": order,
        "form": form,
    })


@login_required
def order_mark_paid(request, order_id):
    """Marca pedido como pago."""
    order = get_object_or_404(
        Order.objects.for_tenant(request.tenant),
        id=order_id,
    )

    try:
        OrderStatusService().mark_as_paid(
            order=order,
            actor=request.user,
        )
        messages.success(request, f"Pedido {order.code} marcado como pago!")
    except ValueError as e:
        messages.error(request, str(e))

    return redirect("order_list")


@login_required
def order_label(request, order_id):
    """Etiqueta de impressão do pedido."""
    order = get_object_or_404(
        Order.objects.for_tenant(request.tenant).select_related("customer"),
        id=order_id,
    )

    return render(request, "orders/order_label.html", {"order": order})


@login_required
def order_edit(request, order_id):
    """Edição de pedido."""
    order = get_object_or_404(
        Order.objects.for_tenant(request.tenant).select_related("customer"),
        id=order_id,
    )
    
    # Não permite editar pedidos finalizados ou cancelados
    if order.order_status in [OrderStatus.COMPLETED, OrderStatus.CANCELLED]:
        messages.error(request, "Este pedido não pode ser editado.")
        return redirect("order_detail", order_id=order_id)
    
    if request.method == "POST":
        total_value = request.POST.get("total_value", "").replace(",", ".")
        delivery_address = request.POST.get("delivery_address", "").strip()
        notes = request.POST.get("notes", "").strip()
        
        try:
            order.total_value = float(total_value) if total_value else order.total_value
            order.delivery_address = delivery_address
            order.notes = notes
            order.save()
            
            messages.success(request, f"Pedido {order.code} atualizado!")
            return redirect("order_detail", order_id=order_id)
        except (ValueError, TypeError):
            messages.error(request, "Valor inválido.")
    
    return render(request, "orders/order_edit.html", {"order": order})
