"""
Admin do app payments
"""

from django.contrib import admin
from apps.payments.models import PaymentLink


@admin.register(PaymentLink)
class PaymentLinkAdmin(admin.ModelAdmin):
    list_display = (
        "description",
        "amount",
        "status",
        "customer_name",
        "order",
        "created_at",
    )
    list_filter = ("status", "tenant", "created_at")
    search_fields = ("description", "customer_name", "pagarme_order_id")
    readonly_fields = (
        "pagarme_order_id",
        "pagarme_charge_id",
        "checkout_url",
        "webhook_data",
        "paid_at",
    )
    raw_id_fields = ("order", "tenant", "created_by")
    date_hierarchy = "created_at"
