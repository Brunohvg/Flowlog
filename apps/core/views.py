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
        # CORREÇÃO: Só conta como receita pedidos pagos E não cancelados/devolvidos
        total_revenue = (
            orders.filter(
                payment_status=PaymentStatus.PAID
            ).exclude(
                order_status__in=[OrderStatus.CANCELLED, OrderStatus.RETURNED]
            ).aggregate(s=Sum("total_value"))["s"]
            or 0
        )
        orders_today = orders.filter(created_at__date=today).count()

        # 2. Dados do Funil (Pipeline) - CORRIGIDO
        # Exclui cancelados/devolvidos do total ativo
        active_orders = orders.exclude(
            order_status__in=[OrderStatus.CANCELLED, OrderStatus.RETURNED]
        )
        total_active = active_orders.count()

        # Cada fase do funil é MUTUAMENTE EXCLUSIVA
        # Pendentes: order_status=PENDING + delivery_status=PENDING (aguardando confirmação)
        pending = active_orders.filter(
            order_status=OrderStatus.PENDING,
            delivery_status=DeliveryStatus.PENDING
        ).count()
        
        # Em processamento: CONFIRMED + delivery ainda PENDING (preparando)
        processing = active_orders.filter(
            order_status=OrderStatus.CONFIRMED,
            delivery_status=DeliveryStatus.PENDING
        ).count()
        
        # Enviados/Prontos: em trânsito ou aguardando retirada
        in_transit = active_orders.filter(
            delivery_status__in=[
                DeliveryStatus.SHIPPED, 
                DeliveryStatus.READY_FOR_PICKUP,
                DeliveryStatus.FAILED_ATTEMPT
            ]
        ).count()
        
        # Concluídos: entregues ou retirados
        delivered = active_orders.filter(
            delivery_status__in=[DeliveryStatus.DELIVERED, DeliveryStatus.PICKED_UP]
        ).count()

        def calc_pct(val, total):
            return int((val / total * 100)) if total > 0 else 0

        stats = {
            "revenue": total_revenue,
            "orders_today": orders_today,
            # Estrutura do Funil corrigida
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
        context["stats"] = stats

        # 3. Alertas (Critical Path)
        alerts = []
        failed = orders.filter(
            delivery_status=DeliveryStatus.FAILED_ATTEMPT
        ).exclude(
            order_status__in=[OrderStatus.CANCELLED, OrderStatus.RETURNED]
        ).count()
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
        
        # Alerta: Retiradas prontas há mais de 24h
        expiring_soon = orders.filter(
            delivery_status=DeliveryStatus.READY_FOR_PICKUP,
            expires_at__lte=timezone.now() + timedelta(hours=12)
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
        
        # Alerta: Pedidos prioritários pendentes
        # CORRIGIDO: Usa Q() com OR para excluir cancelados OU concluídos
        priority_orders = orders.filter(
            is_priority=True
        ).exclude(
            Q(order_status__in=[OrderStatus.CANCELLED, OrderStatus.RETURNED]) |
            Q(delivery_status__in=[DeliveryStatus.DELIVERED, DeliveryStatus.PICKED_UP])
        ).count()
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

        context["alerts"] = alerts

        # 4. Top Clientes
        context["top_customers"] = (
            Customer.objects.filter(tenant=tenant)
            .annotate(
                total_spent=Sum(
                    "orders__total_value",
                    filter=Q(
                        orders__payment_status=PaymentStatus.PAID
                    ) & ~Q(
                        orders__order_status__in=[OrderStatus.CANCELLED, OrderStatus.RETURNED]
                    ),
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
# CONFIGURAÇÕES (Settings) - CORRIGIDO
# ==============================================================================
@login_required
def settings(request):
    """Configurações do Tenant (Loja, WhatsApp, Mensagens)."""
    tenant = request.tenant
    try:
        tenant_settings = tenant.settings
    except (AttributeError, TenantSettings.DoesNotExist):
        tenant_settings = TenantSettings.objects.create(tenant=tenant)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "save_store":
            # Dados da loja
            tenant.name = request.POST.get("store_name", tenant.name)
            tenant.contact_email = request.POST.get("contact_email", tenant.contact_email)
            tenant.contact_phone = request.POST.get("contact_phone", "")
            tenant.address = request.POST.get("address", "")
            tenant.save()
            messages.success(request, "Dados da loja atualizados!")

        elif action == "save_notifications":
            # Controle granular de notificações (checkboxes)
            tenant_settings.whatsapp_enabled = request.POST.get("whatsapp_enabled") == "on"
            tenant_settings.notify_order_created = request.POST.get("notify_order_created") == "on"
            tenant_settings.notify_order_confirmed = request.POST.get("notify_order_confirmed") == "on"
            tenant_settings.notify_payment_received = request.POST.get("notify_payment_received") == "on"
            tenant_settings.notify_payment_refunded = request.POST.get("notify_payment_refunded") == "on"
            tenant_settings.notify_order_shipped = request.POST.get("notify_order_shipped") == "on"
            tenant_settings.notify_order_delivered = request.POST.get("notify_order_delivered") == "on"
            tenant_settings.notify_delivery_failed = request.POST.get("notify_delivery_failed") == "on"
            tenant_settings.notify_order_ready_for_pickup = request.POST.get("notify_order_ready_for_pickup") == "on"
            tenant_settings.notify_order_picked_up = request.POST.get("notify_order_picked_up") == "on"
            tenant_settings.notify_order_expired = request.POST.get("notify_order_expired") == "on"
            tenant_settings.notify_order_cancelled = request.POST.get("notify_order_cancelled") == "on"
            tenant_settings.notify_order_returned = request.POST.get("notify_order_returned") == "on"
            tenant_settings.save()
            messages.success(request, "Configurações de notificações salvas!")

        elif action == "save_messages":
            # TODOS os campos de mensagens
            message_fields = [
                "msg_order_created",
                "msg_order_confirmed",
                "msg_payment_received",
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
    tenant = request.tenant

    if request.method == "POST":
        user.first_name = request.POST.get("first_name", "").strip()
        user.last_name = request.POST.get("last_name", "").strip()

        # Alteração de senha com verificação da senha atual
        current_password = request.POST.get("current_password", "")
        p1 = request.POST.get("new_password", "")
        p2 = request.POST.get("confirm_password", "")
        
        if p1:
            # Só permite trocar senha se informou a senha atual correta
            if not current_password:
                messages.error(request, "Informe a senha atual para alterar.")
            elif not user.check_password(current_password):
                messages.error(request, "Senha atual incorreta.")
            elif p1 != p2:
                messages.error(request, "As senhas não coincidem.")
            elif len(p1) < 6:
                messages.error(request, "A nova senha deve ter pelo menos 6 caracteres.")
            else:
                user.set_password(p1)
                messages.success(
                    request, "Senha alterada com sucesso! Faça login novamente."
                )

        user.save()
        if not p1:
            messages.success(request, "Perfil atualizado!")
        return redirect("profile")

    # Stats filtradas por tenant para consistência
    user_stats = {
        "sales_count": Order.objects.filter(seller=user, tenant=tenant).count() if tenant else 0,
        "sales_total": Order.objects.filter(seller=user, tenant=tenant).aggregate(
            s=Sum("total_value")
        )["s"] or 0 if tenant else 0,
    }

    return render(
        request, "profile/profile.html", {"user": user, "user_stats": user_stats}
    )
