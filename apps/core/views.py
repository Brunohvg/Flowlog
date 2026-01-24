"""
Views principais do sistema: Dashboard, Relatórios, Configurações e Perfil.
Refatorado: Dados blindados, compatível com ApexCharts e Layout Premium.
Usa sale_date para filtros de data (fallback para created_at se null).
"""

import csv
from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Avg, Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView

# Importação dos Models
from apps.orders.models import (
    Customer,
    DeliveryStatus,
    DeliveryType,
    Order,
    OrderStatus,
    PaymentStatus,
)
from apps.tenants.models import TenantSettings

# Import condicional do PaymentLink
try:
    from apps.payments.models import PaymentLink
except ImportError:
    PaymentLink = None


def _parse_date(date_str, default=None):
    """Parse date string (YYYY-MM-DD) to date object."""
    if not date_str:
        return default
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return default


def _get_effective_date_filter(date_from, date_to):
    """
    Retorna filtro Q que usa sale_date quando disponível, senão created_at.
    Isso garante compatibilidade com pedidos antigos sem sale_date.
    """
    return Q(sale_date__gte=date_from, sale_date__lte=date_to) | Q(
        sale_date__isnull=True,
        created_at__date__gte=date_from,
        created_at__date__lte=date_to,
    )


# ==============================================================================
# DASHBOARD
# ==============================================================================


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tenant = self.request.tenant
        today = timezone.now().date()

        # Filtros de data
        date_from = _parse_date(
            self.request.GET.get("date_from"), today - timedelta(days=30)
        )
        date_to = _parse_date(self.request.GET.get("date_to"), today)

        context["date_from"] = date_from
        context["date_to"] = date_to

        # Queryset Base de Pedidos
        orders = Order.objects.filter(tenant=tenant).filter(
            _get_effective_date_filter(date_from, date_to)
        )

        # 1. KPI Principais
        total_revenue = (
            orders.filter(payment_status=PaymentStatus.PAID)
            .exclude(order_status__in=[OrderStatus.CANCELLED, OrderStatus.RETURNED])
            .aggregate(s=Sum("total_value"))["s"]
            or 0
        )

        orders_today = (
            Order.objects.filter(tenant=tenant)
            .filter(
                Q(sale_date=today) | Q(sale_date__isnull=True, created_at__date=today)
            )
            .count()
        )

        # 2. Dados do Funil
        active_orders = orders.exclude(
            order_status__in=[OrderStatus.CANCELLED, OrderStatus.RETURNED]
        )
        total_active = active_orders.count()

        pending = active_orders.filter(
            order_status=OrderStatus.PENDING, delivery_status=DeliveryStatus.PENDING
        ).count()

        processing = active_orders.filter(
            order_status=OrderStatus.CONFIRMED, delivery_status=DeliveryStatus.PENDING
        ).count()

        in_transit = active_orders.filter(
            delivery_status__in=[
                DeliveryStatus.SHIPPED,
                DeliveryStatus.READY_FOR_PICKUP,
                DeliveryStatus.FAILED_ATTEMPT,
            ]
        ).count()

        delivered = active_orders.filter(
            delivery_status__in=[DeliveryStatus.DELIVERED, DeliveryStatus.PICKED_UP]
        ).count()

        def calc_pct(val, total):
            return int((val / total * 100)) if total > 0 else 0

        stats = {
            "revenue": total_revenue,
            "orders_today": orders_today,
            "total_orders": orders.count(),
            "pipeline": {
                "pending": {
                    "count": pending,
                    "pct": calc_pct(pending, total_active),
                    "label": "Aguardando",
                    "icon": "inbox",
                },
                "processing": {
                    "count": processing,
                    "pct": calc_pct(processing, total_active),
                    "label": "Preparação",
                    "icon": "package-open",
                },
                "shipped": {
                    "count": in_transit,
                    "pct": calc_pct(in_transit, total_active),
                    "label": "Em Trânsito",
                    "icon": "truck",
                },
                "delivered": {
                    "count": delivered,
                    "pct": calc_pct(delivered, total_active),
                    "label": "Concluídos",
                    "icon": "check-circle",
                },
            },
            "pending_count": pending,
            "shipped_count": in_transit,
        }
        # 3. Distribuição por Entrega
        delivery_data = active_orders.values("delivery_type").annotate(c=Count("id"))
        delivery_dist = []
        for d in delivery_data:
            d_type = d["delivery_type"]
            label = dict(DeliveryType.choices).get(d_type, d_type)
            icon = "truck"
            if d_type == "motoboy":
                icon = "bike"
            elif d_type == "pickup":
                icon = "store"
            elif d_type == "mandae":
                icon = "package"

            delivery_dist.append(
                {
                    "label": label,
                    "count": d["c"],
                    "pct": calc_pct(d["c"], total_active),
                    "icon": icon,
                }
            )

        stats["delivery_distribution"] = sorted(
            delivery_dist, key=lambda x: x["count"], reverse=True
        )
        context["stats"] = stats

        # 3. Alertas
        alerts = []
        all_orders_global = Order.objects.filter(
            tenant=tenant
        )  # Sem filtro de data para alertas globais

        failed = (
            all_orders_global.filter(delivery_status=DeliveryStatus.FAILED_ATTEMPT)
            .exclude(order_status__in=[OrderStatus.CANCELLED, OrderStatus.RETURNED])
            .count()
        )
        if failed:
            alerts.append(
                {
                    "level": "critical",
                    "icon": "alert-octagon",
                    "title": "Falha na Entrega",
                    "msg": f"{failed} pedidos com erro.",
                    "link": f"?delivery_status={DeliveryStatus.FAILED_ATTEMPT}",
                }
            )

        expiring_soon = all_orders_global.filter(
            delivery_status=DeliveryStatus.READY_FOR_PICKUP,
            expires_at__lte=timezone.now() + timedelta(hours=12),
        ).count()
        if expiring_soon:
            alerts.append(
                {
                    "level": "warning",
                    "icon": "clock",
                    "title": "Retiradas Expirando",
                    "msg": f"{expiring_soon} pedidos com prazo curto.",
                    "link": "?status=ready",
                }
            )

        priority_orders = (
            all_orders_global.filter(is_priority=True)
            .exclude(
                Q(order_status__in=[OrderStatus.CANCELLED, OrderStatus.RETURNED])
                | Q(
                    delivery_status__in=[
                        DeliveryStatus.DELIVERED,
                        DeliveryStatus.PICKED_UP,
                    ]
                )
            )
            .count()
        )
        if priority_orders:
            alerts.append(
                {
                    "level": "critical",
                    "icon": "alert-triangle",
                    "title": "Pedidos Prioritários",
                    "msg": f"{priority_orders} pedidos marcados como urgentes.",
                    "link": "?priority=1",
                }
            )

        if PaymentLink:
            pending_links = PaymentLink.objects.filter(
                tenant=tenant, status="pending"
            ).count()
            if pending_links > 0:
                alerts.append(
                    {
                        "level": "info",
                        "icon": "credit-card",
                        "title": "Links de Pagamento",
                        "msg": f"{pending_links} links aguardando pagamento.",
                        "link": "/pagamentos/?status=pending",
                    }
                )

        context["alerts"] = alerts

        # 4. Top Clientes (CORRIGIDO)
        # O filtro de data precisa ser aplicado explicitamente na relação 'orders__'
        # Usamos Coalesce para garantir que NULL vire 0, permitindo ordenação correta.
        context["top_customers"] = (
            Customer.objects.filter(tenant=tenant)
            .annotate(
                total_spent=Coalesce(
                    Sum(
                        "orders__total_value",
                        filter=Q(orders__payment_status=PaymentStatus.PAID)
                        & (
                            Q(
                                orders__sale_date__gte=date_from,
                                orders__sale_date__lte=date_to,
                            )
                            | Q(
                                orders__sale_date__isnull=True,
                                orders__created_at__date__gte=date_from,
                                orders__created_at__date__lte=date_to,
                            )
                        )
                        & ~Q(
                            orders__order_status__in=[
                                OrderStatus.CANCELLED,
                                OrderStatus.RETURNED,
                            ]
                        ),
                    ),
                    Value(0, output_field=DecimalField()),
                )
            )
            .filter(total_spent__gt=0)  # Mostra apenas quem gastou algo
            .order_by("-total_spent")[:5]
        )

        # 5. Lista Recente
        context["recent_orders"] = (
            Order.objects.filter(tenant=tenant)
            .select_related("customer")
            .order_by("-created_at")[:7]
        )

        return context


# ==============================================================================
# RELATÓRIOS
# ==============================================================================
@login_required
def reports(request):
    tenant = request.tenant
    today = timezone.now().date()

    date_from = _parse_date(request.GET.get("date_from"), today - timedelta(days=30))
    date_to = _parse_date(request.GET.get("date_to"), today)
    status_filter = request.GET.get("status", "")
    payment_filter = request.GET.get("payment", "")
    delivery_filter = request.GET.get("delivery_type", "")

    orders = Order.objects.filter(tenant=tenant).filter(
        _get_effective_date_filter(date_from, date_to)
    )

    if status_filter:
        if status_filter == "pending":
            orders = orders.filter(order_status=OrderStatus.PENDING)
        elif status_filter == "completed":
            orders = orders.filter(order_status=OrderStatus.COMPLETED)
        elif status_filter == "cancelled":
            orders = orders.filter(
                order_status__in=[OrderStatus.CANCELLED, OrderStatus.RETURNED]
            )

    if payment_filter:
        orders = orders.filter(payment_status=payment_filter)

    if delivery_filter:
        orders = orders.filter(delivery_type=delivery_filter)

    summary = orders.aggregate(
        total_orders=Count("id"),
        total_revenue=Sum("total_value"),
        avg_ticket=Avg("total_value"),
    )

    all_orders = Order.objects.filter(tenant=tenant).filter(
        _get_effective_date_filter(date_from, date_to)
    )
    status_data = {
        "pending": all_orders.filter(order_status=OrderStatus.PENDING).count(),
        "shipped": all_orders.filter(delivery_status=DeliveryStatus.SHIPPED).count(),
        "delivered": all_orders.filter(
            delivery_status__in=[DeliveryStatus.DELIVERED, DeliveryStatus.PICKED_UP]
        ).count(),
        "cancelled": all_orders.filter(order_status=OrderStatus.CANCELLED).count(),
    }

    payment_data = {
        "paid": all_orders.filter(payment_status=PaymentStatus.PAID).aggregate(
            count=Count("id"), value=Sum("total_value")
        ),
        "pending": all_orders.filter(payment_status=PaymentStatus.PENDING).aggregate(
            count=Count("id"), value=Sum("total_value")
        ),
    }

    type_data = []
    for dtype, label in DeliveryType.choices:
        data = all_orders.filter(delivery_type=dtype).aggregate(
            count=Count("id"), value=Sum("total_value")
        )
        if data["count"] and data["count"] > 0:
            type_data.append(
                {
                    "type": dtype,
                    "label": label,
                    "count": data["count"],
                    "value": data["value"] or 0,
                }
            )

    # Relatório de Top Clientes (mesma lógica corrigida)
    top_customers = (
        Customer.objects.filter(tenant=tenant)
        .annotate(
            total_orders=Count(
                "orders",
                filter=(
                    Q(orders__sale_date__gte=date_from, orders__sale_date__lte=date_to)
                    | Q(
                        orders__sale_date__isnull=True,
                        orders__created_at__date__gte=date_from,
                        orders__created_at__date__lte=date_to,
                    )
                ),
            ),
            total_value=Coalesce(
                Sum(
                    "orders__total_value",
                    filter=(
                        Q(
                            orders__sale_date__gte=date_from,
                            orders__sale_date__lte=date_to,
                        )
                        | Q(
                            orders__sale_date__isnull=True,
                            orders__created_at__date__gte=date_from,
                            orders__created_at__date__lte=date_to,
                        )
                    ),
                ),
                Value(0, output_field=DecimalField()),
            ),
        )
        .filter(total_orders__gt=0)
        .order_by("-total_value")[:10]
    )

    return render(
        request,
        "reports/reports.html",
        {
            "date_from": date_from,
            "date_to": date_to,
            "status_filter": status_filter,
            "payment_filter": payment_filter,
            "delivery_filter": delivery_filter,
            "summary": summary,
            "status_data": status_data,
            "payment_data": payment_data,
            "type_data": type_data,
            "top_customers": top_customers,
            "orders": orders.select_related("customer")[:100],
        },
    )


@login_required
def reports_csv(request):
    """Exporta relatório em CSV."""
    tenant = request.tenant
    today = timezone.now().date()

    date_from = _parse_date(request.GET.get("date_from"), today - timedelta(days=30))
    date_to = _parse_date(request.GET.get("date_to"), today)

    orders = (
        Order.objects.filter(tenant=tenant)
        .filter(_get_effective_date_filter(date_from, date_to))
        .select_related("customer", "seller")
        .order_by("-created_at")
    )

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="relatorio_{date_from}_{date_to}.csv"'
    )
    response.write("\ufeff")

    writer = csv.writer(response, delimiter=";")
    writer.writerow(
        [
            "Código",
            "Data Venda",
            "Data Registro",
            "Cliente",
            "Telefone",
            "Valor",
            "Pagamento",
            "Status",
            "Entrega",
            "Vendedor",
        ]
    )

    for order in orders:
        sale_dt = (
            order.sale_date.strftime("%d/%m/%Y")
            if order.sale_date
            else order.created_at.strftime("%d/%m/%Y")
        )
        writer.writerow(
            [
                order.code,
                sale_dt,
                order.created_at.strftime("%d/%m/%Y %H:%M"),
                order.customer.name,
                order.customer.phone,
                str(order.total_value).replace(".", ","),
                order.get_payment_status_display(),
                order.get_order_status_display(),
                order.get_delivery_type_display(),
                order.seller.get_full_name() if order.seller else "",
            ]
        )

    return response


# ==============================================================================
# CONFIGURAÇÕES E PERFIL (Mantidos inalterados mas incluídos para completude)
# ==============================================================================
@login_required
def settings(request):
    tenant = request.tenant
    try:
        tenant_settings = tenant.settings
    except (AttributeError, TenantSettings.DoesNotExist):
        tenant_settings = TenantSettings.objects.create(tenant=tenant)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "save_store":
            tenant.name = request.POST.get("store_name", tenant.name)
            tenant.contact_email = request.POST.get(
                "contact_email", tenant.contact_email
            )
            tenant.contact_phone = request.POST.get("contact_phone", "")
            tenant.address = request.POST.get("address", "")
            tenant.save()
            messages.success(request, "Dados da loja atualizados!")

        elif action == "save_notifications":
            tenant_settings.whatsapp_enabled = (
                request.POST.get("whatsapp_enabled") == "on"
            )
            tenant_settings.notify_order_created = (
                request.POST.get("notify_order_created") == "on"
            )
            tenant_settings.notify_order_confirmed = (
                request.POST.get("notify_order_confirmed") == "on"
            )
            tenant_settings.notify_payment_link = (
                request.POST.get("notify_payment_link") == "on"
            )
            tenant_settings.notify_payment_received = (
                request.POST.get("notify_payment_received") == "on"
            )
            tenant_settings.notify_payment_failed = (
                request.POST.get("notify_payment_failed") == "on"
            )
            tenant_settings.notify_payment_refunded = (
                request.POST.get("notify_payment_refunded") == "on"
            )
            tenant_settings.notify_order_shipped = (
                request.POST.get("notify_order_shipped") == "on"
            )
            tenant_settings.notify_order_delivered = (
                request.POST.get("notify_order_delivered") == "on"
            )
            tenant_settings.notify_delivery_failed = (
                request.POST.get("notify_delivery_failed") == "on"
            )
            tenant_settings.notify_order_ready_for_pickup = (
                request.POST.get("notify_order_ready_for_pickup") == "on"
            )
            tenant_settings.notify_order_picked_up = (
                request.POST.get("notify_order_picked_up") == "on"
            )
            tenant_settings.notify_order_expired = (
                request.POST.get("notify_order_expired") == "on"
            )
            tenant_settings.notify_order_cancelled = (
                request.POST.get("notify_order_cancelled") == "on"
            )
            tenant_settings.notify_order_returned = (
                request.POST.get("notify_order_returned") == "on"
            )
            tenant_settings.save()
            messages.success(request, "Configurações de notificações salvas!")

        elif action == "save_messages":
            message_fields = [
                "msg_order_created",
                "msg_order_confirmed",
                "msg_payment_link",
                "msg_payment_received",
                "msg_payment_failed",
                "msg_payment_refunded",
                "msg_order_shipped",
                "msg_order_delivered",
                "msg_delivery_failed",
                "msg_order_ready_for_pickup",
                "msg_order_picked_up",
                "msg_order_expired",
                "msg_order_cancelled",
                "msg_order_returned",
            ]
            for field in message_fields:
                value = request.POST.get(field)
                if value is not None:
                    setattr(tenant_settings, field, value)
            tenant_settings.save()
            messages.success(request, "Mensagens salvas!")

        elif action == "save_pagarme":
            tenant_settings.pagarme_enabled = request.POST.get("pagarme_enabled") == "1"
            tenant_settings.pagarme_pix_enabled = (
                request.POST.get("pagarme_pix_enabled") == "1"
            )
            api_key = request.POST.get("pagarme_api_key", "").strip()
            if api_key:
                tenant_settings.pagarme_api_key = api_key
            try:
                max_installments = int(request.POST.get("pagarme_max_installments", 3))
                if max_installments < 1 or max_installments > 3:
                    max_installments = 3
                tenant_settings.pagarme_max_installments = max_installments
            except (ValueError, TypeError):
                tenant_settings.pagarme_max_installments = 3
            tenant_settings.save()
            messages.success(request, "Configurações do Pagar.me salvas!")

        return redirect("settings")

    return render(
        request,
        "settings/settings.html",
        {"tenant": tenant, "tenant_settings": tenant_settings},
    )


@login_required
def profile(request):
    user = request.user
    tenant = request.tenant

    if request.method == "POST":
        user.first_name = request.POST.get("first_name", "").strip()
        user.last_name = request.POST.get("last_name", "").strip()

        current_password = request.POST.get("current_password", "")
        p1 = request.POST.get("new_password", "")
        p2 = request.POST.get("confirm_password", "")

        if p1:
            if not current_password:
                messages.error(request, "Informe a senha atual para alterar.")
            elif not user.check_password(current_password):
                messages.error(request, "Senha atual incorreta.")
            elif p1 != p2:
                messages.error(request, "As senhas não coincidem.")
            elif len(p1) < 6:
                messages.error(
                    request, "A nova senha deve ter pelo menos 6 caracteres."
                )
            else:
                user.set_password(p1)
                messages.success(
                    request, "Senha alterada com sucesso! Faça login novamente."
                )

        user.save()
        if not p1:
            messages.success(request, "Perfil atualizado!")
        return redirect("profile")

    user_stats = {
        "sales_count": (
            Order.objects.filter(seller=user, tenant=tenant).count() if tenant else 0
        ),
        "sales_total": (
            Order.objects.filter(seller=user, tenant=tenant).aggregate(
                s=Sum("total_value")
            )["s"]
            or 0
            if tenant
            else 0
        ),
    }

    return render(
        request, "profile/profile.html", {"user": user, "user_stats": user_stats}
    )


# ==============================================================================
# CONFIGURAÇÕES DE INTEGRAÇÕES
# ==============================================================================


@login_required
def integrations_settings(request):
    """Página principal de integrações logísticas."""
    tenant = request.tenant
    try:
        tenant_settings = tenant.settings
    except (AttributeError, TenantSettings.DoesNotExist):
        tenant_settings = TenantSettings.objects.create(tenant=tenant)

    return render(
        request,
        "settings/integrations.html",
        {"tenant": tenant, "settings": tenant_settings},
    )


@login_required
def correios_settings(request):
    """Configurações da integração Correios."""
    tenant = request.tenant
    try:
        tenant_settings = tenant.settings
    except (AttributeError, TenantSettings.DoesNotExist):
        tenant_settings = TenantSettings.objects.create(tenant=tenant)

    if request.method == "POST":
        tenant_settings.correios_enabled = request.POST.get("correios_enabled") == "1"
        tenant_settings.correios_usuario = request.POST.get(
            "correios_usuario", ""
        ).strip()

        # Só atualiza código de acesso se foi preenchido (não sobrescreve com vazio)
        codigo_acesso = request.POST.get("correios_codigo_acesso", "").strip()
        if codigo_acesso:
            tenant_settings.correios_codigo_acesso = codigo_acesso
            # Limpa token cacheado para forçar re-autenticação (só se não for token manual novo sendo salvo)
            if not request.POST.get("correios_token"):
                tenant_settings.correios_token = ""
                tenant_settings.correios_token_expira = None

        # Token Manual Opcional
        token_manual = request.POST.get("correios_token", "").strip()
        if token_manual:
            tenant_settings.correios_token = token_manual
            # Se for manual, pode limpar expiração ou setar algo longo
            tenant_settings.correios_token_expira = timezone.now() + timedelta(days=365)

        tenant_settings.correios_contrato = request.POST.get(
            "correios_contrato", ""
        ).strip()
        tenant_settings.correios_cartao_postagem = request.POST.get(
            "correios_cartao_postagem", ""
        ).strip()

        tenant_settings.save()
        messages.success(request, "Configurações dos Correios salvas com sucesso!")
        return redirect("correios_settings")

    return render(
        request,
        "settings/correios.html",
        {"tenant": tenant, "settings": tenant_settings},
    )


@login_required
def mandae_settings(request):
    """Configurações da integração Mandaê."""
    tenant = request.tenant
    try:
        tenant_settings = tenant.settings
    except (AttributeError, TenantSettings.DoesNotExist):
        tenant_settings = TenantSettings.objects.create(tenant=tenant)

    if request.method == "POST":
        tenant_settings.mandae_enabled = request.POST.get("mandae_enabled") == "1"
        tenant_settings.mandae_api_url = request.POST.get(
            "mandae_api_url", "https://api.mandae.com.br/v2/"
        ).strip()

        # Só atualiza token se foi preenchido
        token = request.POST.get("mandae_token", "").strip()
        if token:
            tenant_settings.mandae_token = token

        tenant_settings.mandae_customer_id = request.POST.get(
            "mandae_customer_id", ""
        ).strip()
        tenant_settings.mandae_tracking_prefix = request.POST.get(
            "mandae_tracking_prefix", ""
        ).strip()

        # Webhook secret
        webhook_secret = request.POST.get("mandae_webhook_secret", "").strip()
        if webhook_secret:
            tenant_settings.mandae_webhook_secret = webhook_secret

        tenant_settings.save()
        messages.success(request, "Configurações da Mandaê salvas com sucesso!")
        return redirect("mandae_settings")

    # Gerar URL do webhook para exibição
    webhook_url = request.build_absolute_uri(reverse("mandae:webhook"))

    return render(
        request,
        "settings/mandae.html",
        {
            "tenant": tenant,
            "settings": tenant_settings,
            "webhook_url": webhook_url,
        },
    )


@login_required
def motoboy_settings(request):
    """Configurações de frete Motoboy."""
    tenant = request.tenant
    try:
        tenant_settings = tenant.settings
    except (AttributeError, TenantSettings.DoesNotExist):
        tenant_settings = TenantSettings.objects.create(tenant=tenant)

    if request.method == "POST":
        from decimal import Decimal, InvalidOperation

        tenant_settings.store_cep = request.POST.get("store_cep", "").strip()

        # Preço por km
        try:
            price_per_km = request.POST.get("motoboy_price_per_km", "2.50")
            price_per_km = price_per_km.replace(",", ".")
            tenant_settings.motoboy_price_per_km = Decimal(price_per_km)
        except (InvalidOperation, ValueError):
            tenant_settings.motoboy_price_per_km = Decimal("2.50")

        # Valor mínimo
        try:
            min_price = request.POST.get("motoboy_min_price", "10.00")
            min_price = min_price.replace(",", ".")
            tenant_settings.motoboy_min_price = Decimal(min_price)
        except (InvalidOperation, ValueError):
            tenant_settings.motoboy_min_price = Decimal("10.00")

        # Valor máximo (opcional)
        max_price_str = request.POST.get("motoboy_max_price", "").strip()
        if max_price_str:
            try:
                max_price = max_price_str.replace(",", ".")
                tenant_settings.motoboy_max_price = Decimal(max_price)
            except (InvalidOperation, ValueError):
                tenant_settings.motoboy_max_price = None
        else:
            tenant_settings.motoboy_max_price = None

        # Raio máximo (opcional)
        max_radius_str = request.POST.get("motoboy_max_radius", "").strip()
        if max_radius_str:
            try:
                max_radius = max_radius_str.replace(",", ".")
                tenant_settings.motoboy_max_radius = Decimal(max_radius)
            except (InvalidOperation, ValueError):
                tenant_settings.motoboy_max_radius = None
        else:
            tenant_settings.motoboy_max_radius = None

        # Tentar geocodificar o CEP automaticamente
        if tenant_settings.store_cep:
            try:
                from apps.integrations.freight.services import (
                    NominatimClient,
                    ViaCepClient,
                )

                viacep = ViaCepClient()
                nominatim = NominatimClient()
                cep_info = viacep.get_cep_info(tenant_settings.store_cep)
                if cep_info:
                    address = (
                        f"{cep_info.street}, {cep_info.city}, {cep_info.state}, Brasil"
                    )
                    coords = nominatim.geocode_address(address)
                    if coords:
                        tenant_settings.store_lat, tenant_settings.store_lng = coords
            except Exception:
                pass  # Falha silenciosa no geocoding

        tenant_settings.save()
        messages.success(request, "Configurações de Motoboy salvas com sucesso!")
        return redirect("motoboy_settings")

    return render(
        request,
        "settings/motoboy.html",
        {"tenant": tenant, "settings": tenant_settings},
    )


@login_required
def pagarme_settings(request):
    """Configurações da integração Pagar.me."""
    tenant = request.tenant
    # Tenta obter via relação ou diretamente
    settings = getattr(tenant, "settings", None)

    if not settings:
        settings = TenantSettings.objects.filter(tenant=tenant).first()
        if not settings:
            settings = TenantSettings.objects.create(tenant=tenant)

    if request.method == "POST":
        settings.pagarme_enabled = request.POST.get("pagarme_enabled") == "1"

        api_key = request.POST.get("pagarme_api_key")
        if api_key:
            settings.pagarme_api_key = api_key

        settings.pagarme_max_installments = int(
            request.POST.get("pagarme_max_installments", 3)
        )
        settings.pagarme_pix_enabled = request.POST.get("pagarme_pix_enabled") == "1"

        settings.save()
        messages.success(request, "Configurações do Pagar.me salvas!")
        return redirect("pagarme_settings")

    webhook_url = f"{request.scheme}://{request.get_host()}/pagamentos/webhook/pagarme/"

    return render(
        request,
        "settings/pagarme.html",
        {
            "settings": settings,
            "webhook_url": webhook_url,
        },
    )
