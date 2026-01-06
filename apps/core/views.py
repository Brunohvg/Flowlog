"""
Views principais do sistema: Dashboard, Relatórios, Configurações e Perfil.
Refatorado: Dados blindados, compatível com ApexCharts e Layout Premium.
"""

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Avg, Count, Q, Sum
from django.shortcuts import redirect, render
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

# ==============================================================================
# DASHBOARD (Class-Based View - Moderno + Gráficos)
# ==============================================================================


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tenant = self.request.tenant
        today = timezone.now().date()

        # Queryset Base
        orders = Order.objects.filter(tenant=tenant)

        # 1. KPI Principais
        total_revenue = (
            orders.filter(payment_status=PaymentStatus.PAID).aggregate(
                s=Sum("total_value")
            )["s"]
            or 0
        )
        orders_today = orders.filter(created_at__date=today).count()

        # 2. Dados do Funil (Pipeline)
        # Contamos quantos pedidos estão em cada "fase" macro do processo
        total_active = orders.exclude(
            order_status__in=[OrderStatus.CANCELLED, OrderStatus.RETURNED]
        ).count()

        pending = orders.filter(order_status=OrderStatus.PENDING).count()
        processing = orders.filter(order_status=OrderStatus.CONFIRMED).count()
        shipped = orders.filter(delivery_status=DeliveryStatus.SHIPPED).count()
        delivered = orders.filter(
            delivery_status__in=[DeliveryStatus.DELIVERED, DeliveryStatus.PICKED_UP]
        ).count()

        def calc_pct(val, total):
            return int((val / total * 100)) if total > 0 else 0

        stats = {
            "revenue": total_revenue,
            "orders_today": orders_today,
            # Estrutura do Funil melhorada
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
                    "count": shipped,
                    "pct": calc_pct(shipped, total_active),
                    "label": "Enviados",
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
            "shipped_count": shipped,
        }
        context["stats"] = stats

        # 3. Alertas (Critical Path)
        alerts = []
        failed = orders.filter(delivery_status=DeliveryStatus.FAILED_ATTEMPT).count()
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

        context["alerts"] = alerts

        # 4. Top Clientes (Para preencher o espaço na direita)
        context["top_customers"] = (
            Customer.objects.filter(tenant=tenant)
            .annotate(
                total_spent=Sum(
                    "orders__total_value",
                    filter=Q(orders__payment_status=PaymentStatus.PAID),
                )
            )
            .order_by("-total_spent")[:5]
        )

        # 5. Lista Recente
        context["recent_orders"] = orders.select_related("customer").order_by(
            "-created_at"
        )[:7]

        return context


# ==============================================================================
# RELATÓRIOS (Dados formatados para Tabelas e Gráficos Donut)
# ==============================================================================
@login_required
def reports(request):
    tenant = request.tenant
    today = timezone.now().date()

    # Filtro de Período
    period = request.GET.get("period", "30")
    days_map = {"7": 7, "30": 30, "90": 90, "365": 365}
    days = days_map.get(period, 30)
    start_date = today - timedelta(days=days)

    # Query Base
    orders = Order.objects.filter(tenant=tenant, created_at__date__gte=start_date)

    # 1. Resumo Geral
    summary = orders.aggregate(
        total_orders=Count("id"),
        total_revenue=Sum("total_value"),
        avg_ticket=Avg("total_value"),
    )

    # 2. Dados por Status (Contagens Simples para Gráfico Donut)
    status_data = {
        "pending": orders.filter(order_status=OrderStatus.PENDING).count(),
        "shipped": orders.filter(delivery_status=DeliveryStatus.SHIPPED).count(),
        "delivered": orders.filter(
            delivery_status__in=[DeliveryStatus.DELIVERED, DeliveryStatus.PICKED_UP]
        ).count(),
        "cancelled": orders.filter(order_status=OrderStatus.CANCELLED).count(),
    }

    # 3. Dados Financeiros (Pagos vs Pendentes)
    # IMPORTANTE: Usamos 'count' e 'value' explicitamente para o Template
    payment_data = {
        "paid": orders.filter(payment_status=PaymentStatus.PAID).aggregate(
            count=Count("id"), value=Sum("total_value")
        ),
        "pending": orders.filter(payment_status=PaymentStatus.PENDING).aggregate(
            count=Count("id"), value=Sum("total_value")
        ),
    }

    # 4. Dados por Tipo de Entrega (Lista para Tabela e Gráfico Pie)
    type_data = []
    for dtype, label in DeliveryType.choices:
        data = orders.filter(delivery_type=dtype).aggregate(
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

    # 5. Top Clientes
    top_customers = (
        Customer.objects.filter(tenant=tenant)
        .annotate(
            total_orders=Count(
                "orders", filter=Q(orders__created_at__date__gte=start_date)
            ),
            total_value=Sum(
                "orders__total_value",
                filter=Q(orders__created_at__date__gte=start_date),
            ),
        )
        .filter(total_orders__gt=0)
        .order_by("-total_value")[:10]
    )

    return render(
        request,
        "reports/reports.html",
        {
            "period": period,
            "start_date": start_date,
            "summary": summary,
            "status_data": status_data,
            "payment_data": payment_data,
            "type_data": type_data,
            "top_customers": top_customers,
        },
    )


# ==============================================================================
# CONFIGURAÇÕES (Settings)
# ==============================================================================
@login_required
def settings(request):
    """Configurações do Tenant (Loja, WhatsApp, Mensagens)."""
    tenant = request.tenant
    try:
        tenant_settings = tenant.settings
    except AttributeError:
        tenant_settings = TenantSettings.objects.create(tenant=tenant)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "save_store":
            tenant.name = request.POST.get("store_name")
            tenant.contact_phone = request.POST.get("contact_phone")
            tenant.save()
            messages.success(request, "Dados da loja atualizados!")

        elif action == "save_whatsapp":
            tenant_settings.evolution_api_url = request.POST.get("evolution_api_url")
            tenant_settings.evolution_api_key = request.POST.get("evolution_api_key")
            tenant_settings.evolution_instance = request.POST.get("evolution_instance")
            tenant_settings.whatsapp_enabled = (
                request.POST.get("whatsapp_enabled") == "on"
            )
            tenant_settings.save()
            messages.success(request, "Configurações de WhatsApp salvas!")

        elif action == "save_messages":
            fields = [
                "msg_order_created",
                "msg_order_confirmed",
                "msg_order_shipped",
                "msg_order_delivered",
                "msg_order_ready_for_pickup",
            ]
            for field in fields:
                setattr(tenant_settings, field, request.POST.get(field))
            tenant_settings.save()
            messages.success(request, "Mensagens salvas!")

        return redirect("settings")

    return render(
        request,
        "settings/settings.html",
        {"tenant": tenant, "tenant_settings": tenant_settings},
    )


# ==============================================================================
# PERFIL (Profile)
# ==============================================================================
@login_required
def profile(request):
    """Perfil do usuário logado."""
    user = request.user

    if request.method == "POST":
        user.first_name = request.POST.get("first_name")
        user.last_name = request.POST.get("last_name")

        p1 = request.POST.get("new_password")
        p2 = request.POST.get("confirm_password")
        if p1 and p1 == p2:
            user.set_password(p1)
            messages.success(
                request, "Senha alterada com sucesso! Faça login novamente."
            )
        elif p1:
            messages.error(request, "As senhas não coincidem.")

        user.save()
        if not p1:
            messages.success(request, "Perfil atualizado!")
        return redirect("profile")

    user_stats = {
        "sales_count": Order.objects.filter(seller=user).count(),
        "sales_total": Order.objects.filter(seller=user).aggregate(
            s=Sum("total_value")
        )["s"]
        or 0,
    }

    return render(
        request, "profile/profile.html", {"user": user, "user_stats": user_stats}
    )
