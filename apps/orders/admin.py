# apps/orders/admin.py

from django.contrib import admin
from django.utils.html import format_html

from .models import Customer, Order, OrderActivity


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "phone",
        "email",
        "is_blocked",
        "created_at",
    )
    list_filter = ("is_blocked", "created_at")
    search_fields = ("name", "phone_normalized", "cpf_normalized", "email")
    readonly_fields = ("phone_normalized", "cpf_normalized", "created_at", "updated_at")
    ordering = ("name",)


class OrderActivityInline(admin.TabularInline):
    model = OrderActivity
    extra = 0
    readonly_fields = ("activity_type", "description", "user", "created_at", "metadata")
    can_delete = False
    ordering = ("-created_at",)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "customer",
        "seller",
        "total_value",
        "order_status",
        "payment_status",
        "delivery_status",
        "delivery_type",
        "priority_badge",
        "created_at",
    )

    list_filter = (
        "order_status",
        "payment_status",
        "delivery_status",
        "delivery_type",
        "is_priority",
        "created_at",
    )

    search_fields = (
        "code",
        "customer__name",
        "customer__phone_normalized",
        "tracking_code",
        "pickup_code",
    )

    readonly_fields = (
        "code",
        "created_at",
        "updated_at",
        "shipped_at",
        "delivered_at",
        "cancelled_at",
        "returned_at",
    )

    fieldsets = (
        ("Identificação", {"fields": ("code", "customer", "seller")}),
        ("Valores", {"fields": ("total_value",)}),
        (
            "Status",
            {
                "fields": (
                    "order_status",
                    "payment_status",
                    "delivery_status",
                )
            },
        ),
        (
            "Entrega",
            {
                "fields": (
                    "delivery_type",
                    "delivery_address",
                    "tracking_code",
                    "pickup_code",
                    "expires_at",
                    "delivery_attempts",
                )
            },
        ),
        ("Controle", {"fields": ("is_priority",)}),
        (
            "Cancelamento / Devolução",
            {
                "fields": (
                    "cancel_reason",
                    "cancelled_at",
                    "return_reason",
                    "returned_at",
                )
            },
        ),
        ("Observações", {"fields": ("notes", "internal_notes")}),
        ("Auditoria", {"fields": ("created_at", "updated_at")}),
    )

    inlines = [OrderActivityInline]

    ordering = ("-created_at",)

    def priority_badge(self, obj):
        if obj.is_priority:
            return format_html(
                '<span style="color: red; font-weight: bold;">SIM</span>'
            )
        return "—"

    priority_badge.short_description = "Prioritário"


@admin.register(OrderActivity)
class OrderActivityAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "activity_type",
        "user",
        "created_at",
    )
    list_filter = ("activity_type", "created_at")
    search_fields = ("order__code", "description")
    readonly_fields = (
        "order",
        "activity_type",
        "description",
        "user",
        "metadata",
        "created_at",
    )
    ordering = ("-created_at",)
