from django.contrib import admin

from apps.tenants.models import Tenant, TenantSettings


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active")
    search_fields = ("name", "slug", "contact_email")
    list_filter = ("is_active",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(TenantSettings)
class TenantSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "tenant",
        "pagarme_enabled",
        "correios_enabled",
        "mandae_enabled",
        "whatsapp_enabled",
    )
    list_filter = (
        "pagarme_enabled",
        "correios_enabled",
        "mandae_enabled",
        "whatsapp_enabled",
    )

    fieldsets = (
        (
            "Pagar.me",
            {
                "fields": (
                    "pagarme_enabled",
                    "pagarme_api_key",
                    "pagarme_max_installments",
                    "pagarme_pix_enabled",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Correios",
            {
                "fields": (
                    "correios_enabled",
                    "correios_usuario",
                    "correios_codigo_acesso",
                    "correios_contrato",
                    "correios_cartao_postagem",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Mandaê",
            {
                "fields": (
                    "mandae_enabled",
                    "mandae_api_url",
                    "mandae_token",
                    "mandae_customer_id",
                    "mandae_tracking_prefix",
                    "mandae_webhook_secret",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Motoboy / Frete",
            {
                "fields": (
                    "store_cep",
                    ("store_lat", "store_lng"),
                    "motoboy_price_per_km",
                    ("motoboy_min_price", "motoboy_max_price"),
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "WhatsApp",
            {
                "fields": (
                    "whatsapp_enabled",
                    "evolution_instance",
                    "evolution_instance_token",
                    "whatsapp_number",
                    "whatsapp_connected",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Notificações - Controle",
            {
                "fields": (
                    "notify_order_created",
                    "notify_order_confirmed",
                    "notify_payment_link",
                    "notify_payment_received",
                    "notify_payment_failed",
                    "notify_payment_refunded",
                    "notify_order_shipped",
                    "notify_order_delivered",
                    "notify_delivery_failed",
                    "notify_order_ready_for_pickup",
                    "notify_order_picked_up",
                    "notify_order_expired",
                    "notify_order_cancelled",
                    "notify_order_returned",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Mensagens Personalizadas",
            {
                "fields": (
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
                ),
                "classes": ("collapse",),
            },
        ),
    )

    readonly_fields = ("whatsapp_connected",)
