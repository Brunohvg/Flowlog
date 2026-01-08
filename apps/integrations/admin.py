"""
Admin para logs de integrações - Flowlog.
"""

from django.contrib import admin
from django.utils.html import format_html

from apps.integrations.models import NotificationLog, APIRequestLog


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    """Admin para logs de notificações WhatsApp."""
    
    list_display = [
        'created_at',
        'status_badge',
        'notification_type',
        'order_link',
        'recipient_phone',
        'correlation_id',
        'retry_count',
    ]
    
    list_filter = [
        'status',
        'notification_type',
        'tenant',
        'created_at',
    ]
    
    search_fields = [
        'correlation_id',
        'celery_task_id',
        'recipient_name',
        'recipient_phone',
        'order__code',
        'error_message',
    ]
    
    readonly_fields = [
        'id',
        'correlation_id',
        'celery_task_id',
        'tenant',
        'order',
        'notification_type',
        'status',
        'recipient_phone',
        'recipient_name',
        'message_preview',
        'api_response',
        'error_message',
        'error_code',
        'retry_count',
        'created_at',
        'sent_at',
        'updated_at',
    ]
    
    date_hierarchy = 'created_at'
    ordering = ['-created_at']
    
    fieldsets = [
        ('Identificação', {
            'fields': ['id', 'correlation_id', 'celery_task_id']
        }),
        ('Relacionamentos', {
            'fields': ['tenant', 'order']
        }),
        ('Notificação', {
            'fields': ['notification_type', 'status', 'recipient_phone', 'recipient_name']
        }),
        ('Conteúdo', {
            'fields': ['message_preview'],
            'classes': ['collapse']
        }),
        ('Resposta', {
            'fields': ['api_response', 'error_message', 'error_code', 'retry_count'],
            'classes': ['collapse']
        }),
        ('Timestamps', {
            'fields': ['created_at', 'sent_at', 'updated_at']
        }),
    ]
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
    
    @admin.display(description='Status')
    def status_badge(self, obj):
        colors = {
            'pending': '#f59e0b',   # Amarelo
            'sent': '#10b981',      # Verde
            'failed': '#ef4444',    # Vermelho
            'blocked': '#6b7280',   # Cinza
        }
        color = colors.get(obj.status, '#6b7280')
        return format_html(
            '<span style="background-color: {}; color: white; '
            'padding: 3px 8px; border-radius: 4px; font-size: 11px;">{}</span>',
            color,
            obj.get_status_display()
        )
    
    @admin.display(description='Pedido')
    def order_link(self, obj):
        if obj.order:
            return format_html(
                '<a href="/admin/orders/order/{}/change/">{}</a>',
                obj.order.id,
                obj.order.code
            )
        return '-'


@admin.register(APIRequestLog)
class APIRequestLogAdmin(admin.ModelAdmin):
    """Admin para logs de requisições à API."""
    
    list_display = [
        'created_at',
        'status_badge',
        'method',
        'endpoint_short',
        'instance_name',
        'response_time_display',
        'correlation_id',
    ]
    
    list_filter = [
        'method',
        'status_code',
        'instance_name',
        'created_at',
    ]
    
    search_fields = [
        'correlation_id',
        'endpoint',
        'instance_name',
        'error_message',
    ]
    
    readonly_fields = [
        'id',
        'correlation_id',
        'method',
        'endpoint',
        'instance_name',
        'request_body',
        'status_code',
        'response_body',
        'response_time_ms',
        'error_message',
        'created_at',
    ]
    
    date_hierarchy = 'created_at'
    ordering = ['-created_at']
    
    fieldsets = [
        ('Identificação', {
            'fields': ['id', 'correlation_id']
        }),
        ('Request', {
            'fields': ['method', 'endpoint', 'instance_name', 'request_body']
        }),
        ('Response', {
            'fields': ['status_code', 'response_time_ms', 'response_body']
        }),
        ('Erro', {
            'fields': ['error_message'],
            'classes': ['collapse']
        }),
        ('Timestamp', {
            'fields': ['created_at']
        }),
    ]
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
    
    @admin.display(description='Status')
    def status_badge(self, obj):
        if obj.is_success:
            color = '#10b981'  # Verde
            text = f'{obj.status_code} OK'
        elif obj.status_code == 0:
            color = '#6b7280'  # Cinza
            text = 'Erro Conexão'
        else:
            color = '#ef4444'  # Vermelho
            text = f'{obj.status_code} Erro'
        
        return format_html(
            '<span style="background-color: {}; color: white; '
            'padding: 3px 8px; border-radius: 4px; font-size: 11px;">{}</span>',
            color, text
        )
    
    @admin.display(description='Endpoint')
    def endpoint_short(self, obj):
        endpoint = obj.endpoint
        if len(endpoint) > 50:
            endpoint = endpoint[:47] + '...'
        return endpoint
    
    @admin.display(description='Tempo')
    def response_time_display(self, obj):
        ms = obj.response_time_ms
        if ms >= 1000:
            return format_html(
                '<span style="color: #ef4444;">{:.1f}s</span>',
                ms / 1000
            )
        elif ms >= 500:
            return format_html(
                '<span style="color: #f59e0b;">{}ms</span>',
                ms
            )
        return f'{ms}ms'
