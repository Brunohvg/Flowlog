"""
Views públicas de acompanhamento - Flowlog.
Sistema de rastreamento público com autenticação simples por CPF/Telefone.
"""

from django.shortcuts import get_object_or_404, redirect, render

from apps.orders.models import Customer, Order


def tracking_login(request):
    """
    Página de login para acompanhamento.
    Cliente entra com CPF ou Telefone + últimos 4 dígitos do outro.
    """
    error = None

    if request.method == "POST":
        identifier = request.POST.get("identifier", "").strip()
        verification = request.POST.get("verification", "").strip()

        # Normaliza (remove formatação)
        identifier_digits = "".join(filter(str.isdigit, identifier))
        verification_digits = "".join(filter(str.isdigit, verification))

        if not identifier_digits:
            error = "Digite seu CPF ou telefone."
        elif len(verification_digits) < 4:
            error = "Digite os 4 últimos dígitos para verificação."
        else:
            customers = None

            # Tenta encontrar por CPF (11 dígitos)
            if len(identifier_digits) == 11:
                customers = Customer.objects.filter(cpf_normalized=identifier_digits)
                if customers.exists():
                    # Verifica com últimos 4 do telefone de qualquer um dos clientes
                    valid_customer = None
                    for customer in customers:
                        if customer.last_4_phone == verification_digits[-4:]:
                            valid_customer = customer
                            break

                    if not valid_customer:
                        error = "Código de verificação incorreto."
                    else:
                        # Salva todos os customer_ids com esse CPF na sessão
                        customer_ids = list(customers.values_list("id", flat=True))
                        request.session["tracking_customer_ids"] = [
                            str(cid) for cid in customer_ids
                        ]
                        request.session["tracking_customer_name"] = valid_customer.name
                        request.session["tracking_identifier"] = identifier_digits
                        return redirect("tracking_orders")
                else:
                    error = "CPF não encontrado no sistema."

            # Tenta encontrar por telefone (10-11 dígitos)
            elif len(identifier_digits) >= 10:
                customers = Customer.objects.filter(phone_normalized=identifier_digits)
                if customers.exists():
                    # Verifica com últimos 4 do CPF ou telefone
                    valid_customer = None
                    for customer in customers:
                        # Se tem CPF, verifica com CPF
                        if customer.cpf_normalized:
                            if customer.last_4_cpf == verification_digits[-4:]:
                                valid_customer = customer
                                break
                        else:
                            # Se não tem CPF, aceita últimos 4 do próprio telefone
                            if customer.last_4_phone == verification_digits[-4:]:
                                valid_customer = customer
                                break

                    if not valid_customer:
                        error = "Código de verificação incorreto."
                    else:
                        # Salva todos os customer_ids com esse telefone na sessão
                        customer_ids = list(customers.values_list("id", flat=True))
                        request.session["tracking_customer_ids"] = [
                            str(cid) for cid in customer_ids
                        ]
                        request.session["tracking_customer_name"] = valid_customer.name
                        request.session["tracking_identifier"] = identifier_digits
                        return redirect("tracking_orders")
                else:
                    error = "Telefone não encontrado no sistema."
            else:
                error = "CPF deve ter 11 dígitos ou telefone deve ter 10-11 dígitos."

    return render(request, "tracking/login.html", {"error": error})


def tracking_logout(request):
    """Logout do sistema de acompanhamento."""
    request.session.pop("tracking_customer_ids", None)
    request.session.pop("tracking_customer_name", None)
    request.session.pop("tracking_identifier", None)
    return redirect("tracking_login")


def tracking_orders(request):
    """Lista de pedidos do cliente autenticado."""
    customer_ids = request.session.get("tracking_customer_ids")

    if not customer_ids:
        return redirect("tracking_login")

    # Busca pedidos de todos os customers (pode ser de lojas diferentes)
    orders = (
        Order.objects.filter(customer_id__in=customer_ids)
        .select_related("customer", "tenant")
        .order_by("-created_at")[:50]
    )

    customer_name = request.session.get("tracking_customer_name", "Cliente")

    return render(
        request,
        "tracking/orders.html",
        {
            "customer_name": customer_name,
            "orders": orders,
        },
    )


def tracking_detail(request, code):
    """Detalhes do pedido para cliente autenticado."""
    customer_ids = request.session.get("tracking_customer_ids")

    order = get_object_or_404(
        Order.objects.select_related("customer", "tenant"), code__iexact=code
    )

    # Se não está logado ou pedido não é do cliente, mostra versão pública
    if not customer_ids or str(order.customer_id) not in customer_ids:
        return render(request, "tracking/detail_public.html", {"order": order})

    # Pedido do cliente - mostra versão completa
    activities = order.activities.order_by("-created_at")[:10]

    return render(
        request,
        "tracking/detail.html",
        {
            "order": order,
            "customer_name": request.session.get("tracking_customer_name", "Cliente"),
            "activities": activities,
        },
    )


def tracking_search(request):
    """Busca rápida por código do pedido ou CPF (sem login)."""
    query = request.GET.get("q", "").strip()
    orders = None
    not_found = False

    if query:
        # Normaliza (remove formatação)
        query_digits = "".join(filter(str.isdigit, query))

        # Se parece com código de pedido (começa com PED- ou tem 5+ chars alfanuméricos)
        if query.upper().startswith("PED-") or (len(query) >= 5 and not query_digits):
            try:
                order = Order.objects.get(code__iexact=query)
                return redirect("tracking_detail", code=order.code)
            except Order.DoesNotExist:
                not_found = True

        # Se tem 11 dígitos, busca por CPF
        elif len(query_digits) == 11:
            customers = Customer.objects.filter(cpf_normalized=query_digits)
            if customers.exists():
                orders = (
                    Order.objects.filter(customer__in=customers)
                    .select_related("customer", "tenant")
                    .order_by("-created_at")[:20]
                )

                if not orders.exists():
                    not_found = True
                    orders = None
            else:
                not_found = True

        # Tenta buscar como código mesmo assim
        else:
            try:
                order = Order.objects.get(code__iexact=query)
                return redirect("tracking_detail", code=order.code)
            except Order.DoesNotExist:
                # Tenta buscar parcial no código
                orders = Order.objects.filter(code__icontains=query).select_related(
                    "customer", "tenant"
                )[:10]

                if not orders.exists():
                    not_found = True
                    orders = None

    return render(
        request,
        "tracking/search.html",
        {
            "query": query,
            "orders": orders,
            "not_found": not_found,
        },
    )
