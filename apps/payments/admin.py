"""
Admin do app payments - Otimizado e Organizado
"""

import json

from django.contrib import admin
from django.utils.html import format_html

from apps.payments.models import PaymentLink


@admin.register(PaymentLink)
class PaymentLinkAdmin(admin.ModelAdmin):
    # Otimização de Banco de Dados (Essencial para não travar)
    list_select_related = ("order", "tenant", "created_by")

    list_display = (
        "id",
        "description_short",
        "amount_formatted",
        "status_display",
        "customer_name",
        "get_order_link",  # Link clicável para o pedido
        "created_at_formatted",
    )

    list_filter = ("status", "tenant", "created_at", "expires_at")

    # Busca segura (Evita erros 500)
    search_fields = (
        "id",
        "description",
        "customer_name",
        "customer_email",
        "customer_phone",
        "pagarme_order_id",
        "pagarme_charge_id",
        # Busca pelo ID do pedido relacionado (se houver campo code no Order, use order__code)
        "order__id",
    )

    readonly_fields = (
        "pagarme_order_id",
        "pagarme_charge_id",
        "checkout_url_link",  # Link clicável
        "formatted_webhook_data",  # JSON bonito
        "paid_at",
        "created_at",
        "updated_at",
        "is_expired_display",
    )

    raw_id_fields = ("order", "tenant", "created_by")
    date_hierarchy = "created_at"

    # Organização visual do formulário de detalhe
    fieldsets = (
        (
            "Informações Básicas",
            {"fields": ("tenant", "description", "amount", "installments", "status")},
        ),
        ("Cliente", {"fields": ("customer_name", "customer_email", "customer_phone")}),
        (
            "Integração Pagar.me",
            {
                "fields": (
                    "pagarme_order_id",
                    "pagarme_charge_id",
                    "checkout_url_link",
                    "is_expired_display",
                )
            },
        ),
        ("Relações", {"fields": ("order", "created_by")}),
        ("Datas", {"fields": ("created_at", "expires_at", "paid_at", "updated_at")}),
        (
            "Dados Técnicos",
            {
                "classes": ("collapse",),  # Esconde por padrão para não poluir
                "fields": ("formatted_webhook_data",),
            },
        ),
    )

    # --- MÉTODOS PERSONALIZADOS ---

    def description_short(self, obj):
        return (
            obj.description[:30] + "..."
            if len(obj.description) > 30
            else obj.description
        )

    description_short.short_description = "Descrição"

    def amount_formatted(self, obj):
        return f"R$ {obj.amount}"

    amount_formatted.short_description = "Valor"

    def created_at_formatted(self, obj):
        return obj.created_at.strftime("%d/%m/%Y %H:%M")

    created_at_formatted.short_description = "Criado em"

    def get_order_link(self, obj):
        if obj.order:
            # Tenta pegar o código do pedido, se não tiver, usa o ID
            display_text = getattr(obj.order, "code", str(obj.order.id))
            # Gera link para o admin do pedido
            return format_html(
                '<a href="/admin/orders/order/{}/change/">{}</a>',
                obj.order.id,
                display_text,
            )
        return "-"

    get_order_link.short_description = "Pedido"

    def checkout_url_link(self, obj):
        if obj.checkout_url:
            return format_html(
                '<a href="{}" target="_blank">Abrir Link de Pagamento ↗</a>',
                obj.checkout_url,
            )
        return "-"

    checkout_url_link.short_description = "URL Checkout"

    def formatted_webhook_data(self, obj):
        """Formata o JSON do webhook para ficar legível"""
        if not obj.webhook_data:
            return "-"
        try:
            # Converte para string bonita com indentação
            json_str = json.dumps(obj.webhook_data, indent=2, ensure_ascii=False)
            # Usa tag <pre> para manter a formatação
            return format_html(
                '<pre style="font-size: 12px; background-color: #f5f5f5; padding: 10px; border-radius: 4px;">{}</pre>',
                json_str,
            )
        except Exception:
            return str(obj.webhook_data)

    formatted_webhook_data.short_description = "Webhook Payload"

    def status_display(self, obj):
        """Coloca cores no status"""
        colors = {
            "paid": "green",
            "pending": "orange",
            "failed": "red",
            "canceled": "gray",
            "refunded": "purple",
        }
        color = colors.get(obj.status, "black")
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display(),
        )

    status_display.short_description = "Status"

    def is_expired_display(self, obj):
        return obj.is_expired

    is_expired_display.boolean = True
    is_expired_display.short_description = "Expirado?"  
