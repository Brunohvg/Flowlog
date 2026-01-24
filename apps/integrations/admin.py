"""
Admin para logs de integrações - Flowlog.
CORRIGIDO: Erro de formatação float no response_time_display.
"""

import json

from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from apps.integrations.models import APIRequestLog, NotificationLog


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    """Admin para logs de notificações WhatsApp."""

    list_select_related = ("tenant", "order")

    list_display = [
        "created_at_fmt",
        "status_badge",
        "notification_type",
        "recipient_info",
        "order_link",
        "retry_count",
    ]

    list_filter = [
        "status",
        "notification_type",
        "tenant",
        "created_at",
    ]

    search_fields = [
        "correlation_id",
        "celery_task_id",
        "recipient_name",
        "recipient_phone",
        "order__code",
        "error_message",
    ]

    readonly_fields = [
        "id",
        "correlation_id",
        "celery_task_id",
        "tenant",
        "order_link_detail",
        "notification_type",
        "status",
        "recipient_phone",
        "recipient_name",
        "message_preview",
        "formatted_api_response",
        "error_message",
        "error_code",
        "retry_count",
        "created_at",
        "sent_at",
        "updated_at",
    ]

    date_hierarchy = "created_at"
    ordering = ["-created_at"]

    fieldsets = [
        ("Identificação", {"fields": ["id", "correlation_id", "celery_task_id"]}),
        ("Contexto", {"fields": ["tenant", "order_link_detail"]}),
        (
            "Envio",
            {
                "fields": [
                    "notification_type",
                    "status",
                    "recipient_name",
                    "recipient_phone",
                ]
            },
        ),
        ("Conteúdo", {"fields": ["message_preview"]}),
        (
            "Diagnóstico (JSON)",
            {
                "fields": [
                    "formatted_api_response",
                    "error_message",
                    "error_code",
                    "retry_count",
                ],
                "classes": ["collapse"],
            },
        ),
        ("Auditoria", {"fields": ["created_at", "sent_at", "updated_at"]}),
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    # --- Métodos de Exibição ---

    def created_at_fmt(self, obj):
        return obj.created_at.strftime("%d/%m %H:%M:%S")

    created_at_fmt.short_description = "Data"

    def recipient_info(self, obj):
        return f"{obj.recipient_name} ({obj.recipient_phone})"

    recipient_info.short_description = "Destinatário"

    def status_badge(self, obj):
        colors = {
            "pending": "#f59e0b",  # Amarelo
            "sent": "#10b981",  # Verde
            "failed": "#ef4444",  # Vermelho
            "blocked": "#6b7280",  # Cinza
        }
        color = colors.get(obj.status, "#6b7280")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 4px; font-weight: bold; font-size: 11px;">{}</span>',
            color,
            obj.get_status_display(),
        )

    status_badge.short_description = "Status"

    def order_link(self, obj):
        if obj.order:
            url = reverse("admin:orders_order_change", args=[obj.order.id])
            return format_html('<a href="{}">{}</a>', url, obj.order.code)
        return "-"

    order_link.short_description = "Pedido"

    def order_link_detail(self, obj):
        if obj.order:
            url = reverse("admin:orders_order_change", args=[obj.order.id])
            return format_html('<a href="{}">Ver Pedido {} ↗</a>', url, obj.order.code)
        return "-"

    order_link_detail.short_description = "Pedido Relacionado"

    def formatted_api_response(self, obj):
        if not obj.api_response:
            return "-"
        try:
            json_str = json.dumps(obj.api_response, indent=2, ensure_ascii=False)
            return format_html(
                '<pre style="background: #f8f9fa; padding: 10px; border-radius: 5px; font-size: 11px;">{}</pre>',
                json_str,
            )
        except Exception:
            return str(obj.api_response)

    formatted_api_response.short_description = "Resposta da API (Formatada)"


@admin.register(APIRequestLog)
class APIRequestLogAdmin(admin.ModelAdmin):
    """Admin para logs de requisições à API."""

    list_display = [
        "created_at_fmt",
        "status_badge",
        "method",
        "endpoint_short",
        "response_time_display",
        "correlation_id",
    ]

    list_filter = [
        "method",
        "status_code",
        "instance_name",
        "created_at",
    ]

    search_fields = [
        "correlation_id",
        "endpoint",
        "instance_name",
        "error_message",
    ]

    readonly_fields = [
        "id",
        "correlation_id",
        "method",
        "endpoint",
        "instance_name",
        "formatted_request_body",
        "status_code",
        "formatted_response_body",
        "response_time_ms",
        "error_message",
        "created_at",
    ]

    date_hierarchy = "created_at"
    ordering = ["-created_at"]

    fieldsets = [
        ("Identificação", {"fields": ["id", "correlation_id", "created_at"]}),
        (
            "Requisição",
            {
                "fields": [
                    "method",
                    "endpoint",
                    "instance_name",
                    "formatted_request_body",
                ]
            },
        ),
        (
            "Resposta",
            {"fields": ["status_code", "response_time_ms", "formatted_response_body"]},
        ),
        ("Erros", {"fields": ["error_message"], "classes": ["collapse"]}),
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def created_at_fmt(self, obj):
        return obj.created_at.strftime("%H:%M:%S.%f")[:-3]

    created_at_fmt.short_description = "Hora"

    def status_badge(self, obj):
        if obj.is_success:
            color = "#10b981"  # Verde
            text = f"{obj.status_code} OK"
        elif obj.status_code == 0:
            color = "#6b7280"  # Cinza
            text = "Timeout/Erro"
        else:
            color = "#ef4444"  # Vermelho
            text = f"{obj.status_code} Erro"

        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 4px; font-weight: bold; font-size: 11px;">{}</span>',
            color,
            text,
        )

    status_badge.short_description = "Status"

    def endpoint_short(self, obj):
        if len(obj.endpoint) > 60:
            return obj.endpoint[:57] + "..."
        return obj.endpoint

    endpoint_short.short_description = "Endpoint"

    def response_time_display(self, obj):
        # CORREÇÃO AQUI: Formatamos o número antes de passar para o format_html
        ms = obj.response_time_ms
        style = ""

        if ms >= 2000:
            style = "color: #ef4444; font-weight: bold;"  # Vermelho (lento)
            text = f"{ms / 1000:.1f}s"
        elif ms >= 800:
            style = "color: #f59e0b; font-weight: bold;"  # Amarelo (atenção)
            text = f"{ms}ms"
        else:
            style = "color: #10b981;"  # Verde (rápido)
            text = f"{ms}ms"

        return format_html('<span style="{}">{}</span>', style, text)

    response_time_display.short_description = "Tempo"

    def _format_json(self, data):
        if not data:
            return "-"
        try:
            json_str = json.dumps(data, indent=2, ensure_ascii=False)
            return format_html(
                '<pre style="background: #f8f9fa; padding: 10px; border-radius: 5px; '
                'font-size: 11px; white-space: pre-wrap;">{}</pre>',
                json_str,
            )
        except Exception:
            return str(data)

    def formatted_request_body(self, obj):
        return self._format_json(obj.request_body)

    formatted_request_body.short_description = "Body da Requisição"

    def formatted_response_body(self, obj):
        return self._format_json(obj.response_body)

    formatted_response_body.short_description = "Body da Resposta"
