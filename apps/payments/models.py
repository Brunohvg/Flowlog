"""
Models do app payments - Integração Pagar.me
"""

from django.db import models
from django.utils import timezone
from datetime import timedelta

from apps.core.models import BaseModel


class PaymentLink(BaseModel):
    """Link de pagamento Pagar.me"""
    
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="payment_links",
    )
    
    # Vínculo opcional com pedido
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payment_links",
    )
    
    # Dados do Pagar.me
    pagarme_order_id = models.CharField(
        "ID do Pedido Pagar.me",
        max_length=100,
        blank=True,
        help_text="Order ID retornado pela API"
    )
    pagarme_charge_id = models.CharField(
        "ID da Cobrança",
        max_length=100,
        blank=True,
        help_text="Charge ID para rastreamento"
    )
    checkout_url = models.URLField(
        "URL do Checkout",
        blank=True,
        help_text="Link para pagamento"
    )
    
    # Dados do pagamento
    amount = models.DecimalField(
        "Valor",
        max_digits=10,
        decimal_places=2,
    )
    installments = models.PositiveIntegerField(
        "Parcelas",
        default=1,
        help_text="1 a 3 parcelas"
    )
    description = models.CharField(
        "Descrição",
        max_length=200,
    )
    
    # Cliente
    customer_name = models.CharField("Nome do Cliente", max_length=200)
    customer_phone = models.CharField("Telefone", max_length=20, blank=True)
    customer_email = models.EmailField("E-mail", blank=True)
    
    # Status
    class Status(models.TextChoices):
        PENDING = "pending", "Aguardando Pagamento"
        PAID = "paid", "Pago"
        FAILED = "failed", "Falhou"
        CANCELED = "canceled", "Cancelado"
        EXPIRED = "expired", "Expirado"
        REFUNDED = "refunded", "Estornado"
    
    status = models.CharField(
        "Status",
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    
    # Timestamps
    expires_at = models.DateTimeField(
        "Expira em",
        null=True,
        blank=True,
    )
    paid_at = models.DateTimeField(
        "Pago em",
        null=True,
        blank=True,
    )
    
    # Dados do webhook (JSON completo para debug)
    webhook_data = models.JSONField(
        "Dados do Webhook",
        default=dict,
        blank=True,
    )
    
    # Quem criou
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payment_links_created",
    )

    class Meta:
        verbose_name = "Link de Pagamento"
        verbose_name_plural = "Links de Pagamento"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["pagarme_order_id"]),
            models.Index(fields=["pagarme_charge_id"]),
        ]

    def __str__(self):
        return f"{self.description} - R$ {self.amount}"

    def save(self, *args, **kwargs):
        # Define expiração de 12 horas se não definida
        if not self.expires_at and not self.pk:
            self.expires_at = timezone.now() + timedelta(hours=12)
        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        """Verifica se o link expirou"""
        if self.status != self.Status.PENDING:
            return False
        if self.expires_at and timezone.now() > self.expires_at:
            return True
        return False

    @property
    def is_payable(self):
        """Verifica se ainda pode ser pago"""
        return self.status == self.Status.PENDING and not self.is_expired

    @property
    def amount_cents(self):
        """Valor em centavos (Pagar.me usa centavos)"""
        return int(self.amount * 100)

    def mark_as_paid(self, webhook_data=None):
        """Marca como pago e atualiza pedido vinculado"""
        self.status = self.Status.PAID
        self.paid_at = timezone.now()
        if webhook_data:
            self.webhook_data = webhook_data
        self.save()
        
        # Atualiza pedido vinculado
        if self.order:
            from apps.orders.models import PaymentStatus
            self.order.payment_status = PaymentStatus.PAID
            self.order.save(update_fields=["payment_status", "updated_at"])

    def mark_as_failed(self, webhook_data=None):
        """Marca como falhou"""
        self.status = self.Status.FAILED
        if webhook_data:
            self.webhook_data = webhook_data
        self.save()

    def mark_as_expired(self):
        """Marca como expirado"""
        self.status = self.Status.EXPIRED
        self.save()
