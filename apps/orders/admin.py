"""
Admin do app orders - Flowlog.
Otimizado para gestão visual e performance.
"""

import json

from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import Customer, Order, OrderActivity


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    # Performance
    list_select_related = ("tenant",)

    list_display = (
        "name",
        "phone_formatted",
        "email",
        "is_blocked_badge",
        "orders_count_link",  # Link para ver pedidos
        "created_at",
    )
    list_filter = ("is_blocked", "created_at", "tenant")
    search_fields = ("name", "phone_normalized", "cpf_normalized", "email")
    readonly_fields = ("phone_normalized", "cpf_normalized", "created_at", "updated_at")
    ordering = ("name",)

    def phone_formatted(self, obj):
        return obj.phone

    phone_formatted.short_description = "Telefone"

    def is_blocked_badge(self, obj):
        if obj.is_blocked:
            return format_html(
                '<span style="color: red; font-weight: bold;">BLOQUEADO</span>'
            )
        return format_html('<span style="color: green;">Ativo</span>')

    is_blocked_badge.short_description = "Status"

    def orders_count_link(self, obj):
        count = obj.orders.count()
        url = (
            reverse("admin:orders_order_changelist") + f"?customer__id__exact={obj.id}"
        )
        return format_html('<a href="{}"><b>{}</b> pedidos</a>', url, count)

    orders_count_link.short_description = "Histórico"


class OrderActivityInline(admin.TabularInline):
    """Histórico de atividades dentro do pedido"""

    model = OrderActivity
    extra = 0
    # Otimização para não carregar users demais

    readonly_fields = (
        "created_at",
        "activity_type",
        "user",
        "description",
        "formatted_metadata",
    )
    can_delete = False
    ordering = ("-created_at",)
    exclude = ("metadata",)  # Esconde o JSON cru

    def formatted_metadata(self, obj):
        if not obj.metadata:
            return "-"
        # Formata o JSON para ficar bonito e não ocupar muito espaço
        json_str = json.dumps(obj.metadata, indent=2, ensure_ascii=False)
        return format_html(
            '<pre style="font-size: 11px; margin: 0; background: transparent;">{}</pre>',
            json_str,
        )

    formatted_metadata.short_description = "Detalhes"


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    # OTIMIZAÇÃO CRÍTICA: Carrega chaves estrangeiras de uma vez
    list_select_related = ("customer", "seller", "tenant")

    list_display = (
        "code",
        "customer_link",
        "total_value_fmt",
        "status_badge",
        "payment_badge",
        "delivery_badge",
        "delivery_type_display",
        "created_at_fmt",
    )

    list_filter = (
        "order_status",
        "payment_status",
        "delivery_status",
        "delivery_type",
        "is_priority",
        "sale_date",
        "created_at",
        "tenant",
    )

    search_fields = (
        "code",
        "customer__name",
        "customer__phone_normalized",
        "customer__cpf_normalized",
        "tracking_code",
        "pickup_code",
    )

    readonly_fields = (
        "code",
        "pickup_code",
        "created_at",
        "updated_at",
        "shipped_at",
        "delivered_at",
        "cancelled_at",
        "returned_at",
    )

    date_hierarchy = "created_at"
    inlines = [OrderActivityInline]
    ordering = ("-created_at",)

    # Organização visual dos campos
    fieldsets = (
        (
            "Identificação",
            {"fields": ("tenant", "code", "customer", "seller", "sale_date")},
        ),
        ("Financeiro", {"fields": ("total_value", "payment_status")}),
        (
            "Logística & Entrega",
            {
                "fields": (
                    "delivery_type",
                    "delivery_status",
                    "delivery_address",
                    "tracking_code",
                    "pickup_code",
                    "expires_at",
                    "delivery_attempts",
                )
            },
        ),
        (
            "Controle de Motoboy",
            {
                "fields": ("motoboy_fee", "motoboy_paid"),
                "classes": ("collapse",),  # Esconde se não usar
            },
        ),
        ("Controle & Prioridade", {"fields": ("order_status", "is_priority")}),
        (
            "Cancelamento / Devolução",
            {
                "fields": (
                    "cancel_reason",
                    "cancelled_at",
                    "return_reason",
                    "returned_at",
                ),
                "classes": ("collapse",),
            },
        ),
        ("Observações", {"fields": ("notes", "internal_notes")}),
        ("Auditoria", {"fields": ("created_at", "updated_at")}),
    )

    # --- Helpers de Exibição ---

    def customer_link(self, obj):
        if obj.customer:
            url = reverse("admin:orders_customer_change", args=[obj.customer.id])
            return format_html('<a href="{}">{}</a>', url, obj.customer.name)
        return "-"

    customer_link.short_description = "Cliente"

    def total_value_fmt(self, obj):
        return f"R$ {obj.total_value}"

    total_value_fmt.short_description = "Valor"

    def created_at_fmt(self, obj):
        return obj.created_at.strftime("%d/%m %H:%M")

    created_at_fmt.short_description = "Data"

    def delivery_type_display(self, obj):
        icon = ""
        if obj.delivery_type == "pickup":
            icon = "🏪 "
        elif obj.delivery_type == "motoboy":
            icon = "🛵 "
        elif obj.delivery_type in ["sedex", "pac"]:
            icon = "📦 "
        return f"{icon}{obj.get_delivery_type_display()}"

    delivery_type_display.short_description = "Tipo"

    # --- Badges Coloridos ---

    def _get_badge(self, text, color):
        # Cores modernas (Tailwind style)
        colors = {
            "green": "#d1fae5; color: #065f46",  # Emerald
            "blue": "#dbeafe; color: #1e40af",  # Blue
            "yellow": "#fef3c7; color: #92400e",  # Amber
            "red": "#fee2e2; color: #991b1b",  # Red
            "gray": "#f3f4f6; color: #1f2937",  # Gray
            "purple": "#f3e8ff; color: #6b21a8",  # Purple
        }
        style = (
            f"background-color: {colors.get(color, colors['gray'])}; "
            f"padding: 3px 8px; border-radius: 10px; font-weight: bold; font-size: 11px;"
        )
        return format_html('<span style="{}">{}</span>', style, text)

    def status_badge(self, obj):
        # Mapeia status -> cores
        color_map = {
            "pending": "yellow",
            "confirmed": "blue",
            "completed": "green",
            "cancelled": "red",
            "returned": "red",
        }
        return self._get_badge(
            obj.get_order_status_display(), color_map.get(obj.order_status, "gray")
        )

    status_badge.short_description = "Status"

    def payment_badge(self, obj):
        color_map = {
            "pending": "yellow",
            "paid": "green",
            "refunded": "purple",
        }
        return self._get_badge(
            obj.get_payment_status_display(), color_map.get(obj.payment_status, "gray")
        )

    payment_badge.short_description = "Pagamento"

    def delivery_badge(self, obj):
        color_map = {
            "pending": "gray",
            "shipped": "blue",
            "ready_for_pickup": "purple",
            "delivered": "green",
            "picked_up": "green",
            "failed_attempt": "yellow",
            "expired": "red",
        }
        return self._get_badge(
            obj.get_delivery_status_display(),
            color_map.get(obj.delivery_status, "gray"),
        )

    delivery_badge.short_description = "Entrega"


@admin.register(OrderActivity)
class OrderActivityAdmin(admin.ModelAdmin):
    list_select_related = ("order", "user")
    list_display = (
        "created_at",
        "order_link",
        "activity_type",
        "user",
        "description_short",
    )
    list_filter = ("activity_type", "created_at")
    search_fields = ("order__code", "description", "user__email")
    readonly_fields = ("created_at", "metadata")

    def order_link(self, obj):
        url = reverse("admin:orders_order_change", args=[obj.order.id])
        return format_html('<a href="{}">{}</a>', url, obj.order.code)

    order_link.short_description = "Pedido"

    def description_short(self, obj):
        return (
            (obj.description[:75] + "...")
            if len(obj.description) > 75
            else obj.description
        )

    description_short.short_description = "Descrição"
