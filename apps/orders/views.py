from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from apps.orders.models import Order
from apps.orders.services import OrderService, OrderStatusService


@login_required
def order_list(request):
    """
    Lista principal de pedidos (tela operacional).
    View apenas consulta e renderiza.
    """
    orders = (
        Order.objects.for_tenant(request.tenant)
        .select_related("customer", "seller")
        .order_by("-created_at")
    )

    return render(request, "orders/order_list.html", {"orders": orders})


@login_required
def order_create(request):
    """
    Criação de pedido.
    Nenhuma regra de negócio aqui.
    """
    if request.method == "POST":
        OrderService().create_order(
            tenant=request.tenant,
            seller=request.user,
            data=request.POST,
        )
        return redirect("order_list")

    return render(request, "orders/order_create.html")


@login_required
def order_mark_shipped(request, order_id):
    """
    Marca pedido como enviado.
    Apenas delega para o service.
    """
    order = get_object_or_404(
        Order.objects.for_tenant(request.tenant),
        id=order_id,
    )

    OrderStatusService().mark_as_shipped(
        order=order,
        actor=request.user,
    )

    return redirect("order_list")


@login_required
def order_mark_delivered(request, order_id):
    """
    Marca pedido como entregue.
    Apenas delega para o service.
    """
    order = get_object_or_404(
        Order.objects.for_tenant(request.tenant),
        id=order_id,
    )

    OrderStatusService().mark_as_delivered(
        order=order,
        actor=request.user,
    )

    return redirect("order_list")


@login_required
def order_ready_for_pickup(request, order_id):
    """
    Marca pedido como pronto para retirada.
    Apenas delega para o service.
    """
    order = get_object_or_404(
        Order.objects.for_tenant(request.tenant),
        id=order_id,
    )

    OrderStatusService().mark_ready_for_pickup(
        order=order,
        actor=request.user,
    )

    return redirect("order_list")


@login_required
def order_label(request, order_id):
    """
    Etiqueta de impressão do pedido.
    View apenas busca e renderiza.
    """
    order = get_object_or_404(
        Order.objects.for_tenant(request.tenant),
        id=order_id,
    )

    return render(request, "orders/order_label.html", {"order": order})
