"""
Views principais do sistema: Dashboard, Relatórios, Configurações e Perfil.
Refatorado: Dados blindados, compatível com ApexCharts e Layout Premium.
Usa sale_date para filtros de data (fallback para created_at se null).
"""

import csv
from datetime import timedelta, datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Avg, Count, Q, Sum, F
from django.db.models.functions import Coalesce, TruncDate
from django.http import HttpResponse
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

# Import condicional do PaymentLink (pode não existir em versões antigas)
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
    return (
        Q(sale_date__gte=date_from, sale_date__lte=date_to) |
        Q(sale_date__isnull=True, created_at__date__gte=date_from, created_at__date__lte=date_to)
    )


# ==============================================================================
# DASHBOARD (Class-Based View - Moderno + Gráficos)
# ==============================================================================


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tenant = self.request.tenant
        today = timezone.now().date()

        # Filtros de data
        date_from = _parse_date(self.request.GET.get('date_from'), today - timedelta(days=30))
        date_to = _parse_date(self.request.GET.get('date_to'), today)
        
        context['date_from'] = date_from
        context['date_to'] = date_to

        # Queryset Base com filtro de data (usa sale_date ou created_at)
        orders = Order.objects.filter(tenant=tenant).filter(
            _get_effective_date_filter(date_from, date_to)
        )

        # 1. KPI Principais
        total_revenue = (
            orders.filter(
                payment_status=PaymentStatus.PAID
            ).exclude(
                order_status__in=[OrderStatus.CANCELLED, OrderStatus.RETURNED]
            ).aggregate(s=Sum("total_value"))["s"]
            or 0
        )
        
        # Pedidos de hoje (usa sale_date se disponível)
        orders_today = Order.objects.filter(tenant=tenant).filter(
            Q(sale_date=today) | Q(sale_date__isnull=True, created_at__date=today)
        ).count()

        # 2. Dados do Funil (Pipeline)
        active_orders = orders.exclude(
            order_status__in=[OrderStatus.CANCELLED, OrderStatus.RETURNED]
        )
        total_active = active_orders.count()

        pending = active_orders.filter(
            order_status=OrderStatus.PENDING,
            delivery_status=DeliveryStatus.PENDING
        ).count()
        
        processing = active_orders.filter(
            order_status=OrderStatus.CONFIRMED,
            delivery_status=DeliveryStatus.PENDING
        ).count()
        
        in_transit = active_orders.filter(
            delivery_status__in=[
                DeliveryStatus.SHIPPED, 
                DeliveryStatus.READY_FOR_PICKUP,
                DeliveryStatus.FAILED_ATTEMPT
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
                "pending": {"count": pending, "pct": calc_pct(pending, total_active), "label": "Aguardando", "icon": "inbox"},
                "processing": {"count": processing, "pct": calc_pct(processing, total_active), "label": "Preparação", "icon": "package-open"},
                "shipped": {"count": in_transit, "pct": calc_pct(in_transit, total_active), "label": "Em Trânsito", "icon": "truck"},
                "delivered": {"count": delivered, "pct": calc_pct(delivered, total_active), "label": "Concluídos", "icon": "check-circle"},
            },
            "pending_count": pending,
            "shipped_count": in_transit,
        }
        context["stats"] = stats

        # 3. Alertas (sempre globais, não filtrados por data)
        alerts = []
        all_orders = Order.objects.filter(tenant=tenant)
        
        failed = all_orders.filter(
            delivery_status=DeliveryStatus.FAILED_ATTEMPT
        ).exclude(
            order_status__in=[OrderStatus.CANCELLED, OrderStatus.RETURNED]
        ).count()
        if failed:
            alerts.append({"level": "critical", "icon": "alert-octagon", "title": "Falha na Entrega", "msg": f"{failed} pedidos com erro.", "link": f"?delivery_status={DeliveryStatus.FAILED_ATTEMPT}"})
        
        expiring_soon = all_orders.filter(
            delivery_status=DeliveryStatus.READY_FOR_PICKUP,
            expires_at__lte=timezone.now() + timedelta(hours=12)
        ).count()
        if expiring_soon:
            alerts.append({"level": "warning", "icon": "clock", "title": "Retiradas Expirando", "msg": f"{expiring_soon} pedidos com prazo curto.", "link": "?status=ready"})
        
        priority_orders = all_orders.filter(is_priority=True).exclude(
            Q(order_status__in=[OrderStatus.CANCELLED, OrderStatus.RETURNED]) |
            Q(delivery_status__in=[DeliveryStatus.DELIVERED, DeliveryStatus.PICKED_UP])
        ).count()
        if priority_orders:
            alerts.append({"level": "critical", "icon": "alert-triangle", "title": "Pedidos Prioritários", "msg": f"{priority_orders} pedidos marcados como urgentes.", "link": "?priority=1"})

        # Alerta de links de pagamento pendentes (se Pagar.me estiver habilitado)
        if PaymentLink:
            pending_links = PaymentLink.objects.filter(
                tenant=tenant,
                status="pending"
            ).count()
            if pending_links > 0:
                alerts.append({
                    "level": "info", 
                    "icon": "credit-card", 
                    "title": "Links de Pagamento", 
                    "msg": f"{pending_links} links aguardando pagamento.",
                    "link": "/pagamentos/?status=pending"
                })

        context["alerts"] = alerts

        # 4. Top Clientes (período)
        context["top_customers"] = (
            Customer.objects.filter(tenant=tenant)
            .annotate(
                total_spent=Sum(
                    "orders__total_value",
                    filter=Q(
                        orders__payment_status=PaymentStatus.PAID
                    ) & (
                        Q(orders__sale_date__gte=date_from, orders__sale_date__lte=date_to) |
                        Q(orders__sale_date__isnull=True, orders__created_at__date__gte=date_from, orders__created_at__date__lte=date_to)
                    ) & ~Q(
                        orders__order_status__in=[OrderStatus.CANCELLED, OrderStatus.RETURNED]
                    ),
                )
            )
            .order_by("-total_spent")[:5]
        )

        # 5. Lista Recente
        context["recent_orders"] = Order.objects.filter(tenant=tenant).select_related("customer").order_by("-created_at")[:7]

        return context


# ==============================================================================
# RELATÓRIOS (Dados formatados para Tabelas e Gráficos Donut)
# ==============================================================================
@login_required
def reports(request):
    tenant = request.tenant
    today = timezone.now().date()

    # Filtros
    date_from = _parse_date(request.GET.get('date_from'), today - timedelta(days=30))
    date_to = _parse_date(request.GET.get('date_to'), today)
    status_filter = request.GET.get('status', '')
    payment_filter = request.GET.get('payment', '')
    delivery_filter = request.GET.get('delivery_type', '')

    # Query Base usando sale_date
    orders = Order.objects.filter(tenant=tenant).filter(
        _get_effective_date_filter(date_from, date_to)
    )

    # Aplicar filtros adicionais
    if status_filter:
        if status_filter == 'pending':
            orders = orders.filter(order_status=OrderStatus.PENDING)
        elif status_filter == 'completed':
            orders = orders.filter(order_status=OrderStatus.COMPLETED)
        elif status_filter == 'cancelled':
            orders = orders.filter(order_status__in=[OrderStatus.CANCELLED, OrderStatus.RETURNED])
    
    if payment_filter:
        orders = orders.filter(payment_status=payment_filter)
    
    if delivery_filter:
        orders = orders.filter(delivery_type=delivery_filter)

    # 1. Resumo Geral
    summary = orders.aggregate(
        total_orders=Count("id"),
        total_revenue=Sum("total_value"),
        avg_ticket=Avg("total_value"),
    )

    # 2. Dados por Status (usando filtro de data)
    all_orders = Order.objects.filter(tenant=tenant).filter(
        _get_effective_date_filter(date_from, date_to)
    )
    status_data = {
        "pending": all_orders.filter(order_status=OrderStatus.PENDING).count(),
        "shipped": all_orders.filter(delivery_status=DeliveryStatus.SHIPPED).count(),
        "delivered": all_orders.filter(delivery_status__in=[DeliveryStatus.DELIVERED, DeliveryStatus.PICKED_UP]).count(),
        "cancelled": all_orders.filter(order_status=OrderStatus.CANCELLED).count(),
    }

    # 3. Dados Financeiros
    payment_data = {
        "paid": all_orders.filter(payment_status=PaymentStatus.PAID).aggregate(count=Count("id"), value=Sum("total_value")),
        "pending": all_orders.filter(payment_status=PaymentStatus.PENDING).aggregate(count=Count("id"), value=Sum("total_value")),
    }

    # 4. Dados por Tipo de Entrega
    type_data = []
    for dtype, label in DeliveryType.choices:
        data = all_orders.filter(delivery_type=dtype).aggregate(count=Count("id"), value=Sum("total_value"))
        if data["count"] and data["count"] > 0:
            type_data.append({"type": dtype, "label": label, "count": data["count"], "value": data["value"] or 0})

    # 5. Top Clientes
    top_customers = (
        Customer.objects.filter(tenant=tenant)
        .annotate(
            total_orders=Count(
                "orders", 
                filter=(
                    Q(orders__sale_date__gte=date_from, orders__sale_date__lte=date_to) |
                    Q(orders__sale_date__isnull=True, orders__created_at__date__gte=date_from, orders__created_at__date__lte=date_to)
                )
            ),
            total_value=Sum(
                "orders__total_value", 
                filter=(
                    Q(orders__sale_date__gte=date_from, orders__sale_date__lte=date_to) |
                    Q(orders__sale_date__isnull=True, orders__created_at__date__gte=date_from, orders__created_at__date__lte=date_to)
                )
            ),
        )
        .filter(total_orders__gt=0)
        .order_by("-total_value")[:10]
    )

    return render(request, "reports/reports.html", {
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
    })


@login_required
def reports_csv(request):
    """Exporta relatório em CSV."""
    tenant = request.tenant
    today = timezone.now().date()

    date_from = _parse_date(request.GET.get('date_from'), today - timedelta(days=30))
    date_to = _parse_date(request.GET.get('date_to'), today)

    orders = Order.objects.filter(tenant=tenant).filter(
        _get_effective_date_filter(date_from, date_to)
    ).select_related("customer", "seller").order_by("-created_at")

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="relatorio_{date_from}_{date_to}.csv"'
    response.write('\ufeff')  # BOM para Excel

    writer = csv.writer(response, delimiter=';')
    writer.writerow(['Código', 'Data Venda', 'Data Registro', 'Cliente', 'Telefone', 'Valor', 'Pagamento', 'Status', 'Entrega', 'Vendedor'])

    for order in orders:
        sale_dt = order.sale_date.strftime('%d/%m/%Y') if order.sale_date else order.created_at.strftime('%d/%m/%Y')
        writer.writerow([
            order.code,
            sale_dt,
            order.created_at.strftime('%d/%m/%Y %H:%M'),
            order.customer.name,
            order.customer.phone,
            str(order.total_value).replace('.', ','),
            order.get_payment_status_display(),
            order.get_order_status_display(),
            order.get_delivery_type_display(),
            order.seller.get_full_name() if order.seller else '',
        ])

    return response


# ==============================================================================
# CONFIGURAÇÕES (Settings)
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
            tenant.name = request.POST.get("store_name", tenant.name)
            tenant.contact_email = request.POST.get("contact_email", tenant.contact_email)
            tenant.contact_phone = request.POST.get("contact_phone", "")
            tenant.address = request.POST.get("address", "")
            tenant.save()
            messages.success(request, "Dados da loja atualizados!")

        elif action == "save_notifications":
            tenant_settings.whatsapp_enabled = request.POST.get("whatsapp_enabled") == "on"
            tenant_settings.notify_order_created = request.POST.get("notify_order_created") == "on"
            tenant_settings.notify_order_confirmed = request.POST.get("notify_order_confirmed") == "on"
            tenant_settings.notify_payment_link = request.POST.get("notify_payment_link") == "on"
            tenant_settings.notify_payment_received = request.POST.get("notify_payment_received") == "on"
            tenant_settings.notify_payment_failed = request.POST.get("notify_payment_failed") == "on"
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
            message_fields = [
                "msg_order_created", "msg_order_confirmed", "msg_payment_link", "msg_payment_received", 
                "msg_payment_failed", "msg_payment_refunded",
                "msg_order_shipped", "msg_order_delivered", "msg_delivery_failed", "msg_order_ready_for_pickup",
                "msg_order_picked_up", "msg_order_expired", "msg_order_cancelled", "msg_order_returned",
            ]
            for field in message_fields:
                value = request.POST.get(field)
                if value is not None:
                    setattr(tenant_settings, field, value)
            tenant_settings.save()
            messages.success(request, "Mensagens salvas!")

        elif action == "save_pagarme":
            tenant_settings.pagarme_enabled = request.POST.get("pagarme_enabled") == "1"
            tenant_settings.pagarme_pix_enabled = request.POST.get("pagarme_pix_enabled") == "1"
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

    return render(request, "settings/settings.html", {"tenant": tenant, "tenant_settings": tenant_settings})


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
                messages.error(request, "A nova senha deve ter pelo menos 6 caracteres.")
            else:
                user.set_password(p1)
                messages.success(request, "Senha alterada com sucesso! Faça login novamente.")

        user.save()
        if not p1:
            messages.success(request, "Perfil atualizado!")
        return redirect("profile")

    user_stats = {
        "sales_count": Order.objects.filter(seller=user, tenant=tenant).count() if tenant else 0,
        "sales_total": Order.objects.filter(seller=user, tenant=tenant).aggregate(s=Sum("total_value"))["s"] or 0 if tenant else 0,
    }

    return render(request, "profile/profile.html", {"user": user, "user_stats": user_stats})
