"""
Models para logging de integrações - Flowlog.

Registra todas as tentativas de envio de notificações e chamadas à API
para diagnóstico de problemas e auditoria.
"""

import uuid
from django.db import models
from django.utils import timezone


class NotificationLog(models.Model):
    """
    Log de tentativas de envio de notificações WhatsApp.

    Registra cada tentativa de envio, permitindo:
    - Diagnóstico de falhas
    - Auditoria de mensagens enviadas
    - Análise de taxa de sucesso
    - Rastreamento de ponta a ponta via correlation_id
    """

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pendente'
        SENT = 'sent', 'Enviado'
        FAILED = 'failed', 'Falhou'
        BLOCKED = 'blocked', 'Bloqueado'

    class NotificationType(models.TextChoices):
        ORDER_CREATED = 'order_created', 'Pedido Criado'
        ORDER_CONFIRMED = 'order_confirmed', 'Pedido Confirmado'
        PAYMENT_RECEIVED = 'payment_received', 'Pagamento Recebido'
        PAYMENT_REFUNDED = 'payment_refunded', 'Pagamento Estornado'
        ORDER_SHIPPED = 'order_shipped', 'Pedido Enviado'
        ORDER_DELIVERED = 'order_delivered', 'Pedido Entregue'
        DELIVERY_FAILED = 'delivery_failed', 'Entrega Falhou'
        READY_FOR_PICKUP = 'ready_for_pickup', 'Pronto para Retirada'
        PICKED_UP = 'picked_up', 'Retirado'
        EXPIRED = 'expired', 'Expirado'
        CANCELLED = 'cancelled', 'Cancelado'
        RETURNED = 'returned', 'Devolvido'

    # Identificação
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    correlation_id = models.CharField(
        max_length=50,
        db_index=True,
        help_text="ID de correlação para rastreamento de ponta a ponta"
    )
    celery_task_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        db_index=True,
        help_text="ID da task Celery que originou o envio"
    )

    # Relacionamentos
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='notification_logs'
    )
    order = models.ForeignKey(
        'orders.Order',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notification_logs'
    )

    # Dados da notificação
    notification_type = models.CharField(
        max_length=50,
        choices=NotificationType.choices,
        db_index=True
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True
    )

    # Destinatário (mascarado para privacidade)
    recipient_phone = models.CharField(
        max_length=20,
        help_text="Últimos 4 dígitos do telefone"
    )
    recipient_name = models.CharField(max_length=200, blank=True)

    # Conteúdo
    message_preview = models.TextField(
        max_length=500,
        blank=True,
        help_text="Preview da mensagem (truncado)"
    )

    # Resposta da API
    api_response = models.JSONField(
        null=True,
        blank=True,
        help_text="Resposta completa da Evolution API"
    )

    # Erro
    error_message = models.TextField(blank=True, default="")
    error_code = models.CharField(max_length=50, blank=True, default="")

    # Retry
    retry_count = models.PositiveSmallIntegerField(default=0)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'created_at']),
            models.Index(fields=['order', 'notification_type']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['notification_type', 'status']),
        ]
        verbose_name = 'Log de Notificação'
        verbose_name_plural = 'Logs de Notificações'

    def __str__(self):
        return f"{self.notification_type} - {self.status} - {self.correlation_id}"

    def mark_sent(self, api_response: dict = None):
        """Marca notificação como enviada."""
        self.status = self.Status.SENT
        self.sent_at = timezone.now()
        if api_response:
            self.api_response = api_response
        self.save(update_fields=['status', 'sent_at', 'api_response', 'updated_at'])

    def mark_failed(
        self,
        error_message: str = None,
        error_code: str = None,
        api_response: dict = None
    ):
        """Marca notificação como falha."""
        self.status = self.Status.FAILED
        if error_message:
            self.error_message = error_message
        if error_code:
            self.error_code = str(error_code)
        if api_response:
            self.api_response = api_response
        self.retry_count += 1
        self.save(update_fields=[
            'status', 'error_message', 'error_code',
            'api_response', 'retry_count', 'updated_at'
        ])

    def mark_blocked(self, reason: str = None):
        """Marca notificação como bloqueada."""
        self.status = self.Status.BLOCKED
        if reason:
            self.error_message = reason
        self.save(update_fields=['status', 'error_message', 'updated_at'])


class APIRequestLog(models.Model):
    """
    Log de requisições à Evolution API.

    Registra todas as chamadas HTTP para:
    - Diagnóstico de problemas de comunicação
    - Análise de performance (tempo de resposta)
    - Auditoria de operações
    - Debug de respostas inesperadas
    """

    # Identificação
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    correlation_id = models.CharField(
        max_length=50,
        db_index=True,
        help_text="ID de correlação para rastreamento"
    )

    # Request
    method = models.CharField(max_length=10)  # GET, POST, PUT, DELETE
    endpoint = models.CharField(max_length=500)
    instance_name = models.CharField(max_length=100, blank=True, null=True)
    request_body = models.JSONField(null=True, blank=True)

    # Response
    status_code = models.IntegerField(default=0)
    response_body = models.JSONField(null=True, blank=True)
    response_time_ms = models.IntegerField(
        default=0,
        help_text="Tempo de resposta em milissegundos"
    )

    # Erro
    error_message = models.TextField(blank=True, default="")

    # Timestamp
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['correlation_id', 'created_at']),
            models.Index(fields=['instance_name', 'created_at']),
            models.Index(fields=['status_code', 'created_at']),
            models.Index(fields=['endpoint', 'status_code']),
        ]
        verbose_name = 'Log de Requisição API'
        verbose_name_plural = 'Logs de Requisições API'

    def __str__(self):
        return f"{self.method} {self.endpoint} - {self.status_code}"

    @property
    def is_success(self) -> bool:
        """Retorna True se a requisição foi bem sucedida."""
        return 200 <= self.status_code < 300

    @property
    def is_error(self) -> bool:
        """Retorna True se a requisição falhou."""
        return self.status_code >= 400 or self.status_code == 0
