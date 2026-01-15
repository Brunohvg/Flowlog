"""
Models do app payments - Integração Pagar.me
"""

from datetime import timedelta

from django.db import models, transaction as db_transaction
from django.utils import timezone

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
        help_text="Order ID retornado pela API",
    )
    pagarme_charge_id = models.CharField(
        "ID da Cobrança",
        max_length=100,
        blank=True,
        help_text="Charge ID para rastreamento",
    )
    checkout_url = models.URLField(
        "URL do Checkout", blank=True, help_text="Link para pagamento"
    )

    # Dados do pagamento
    amount = models.DecimalField(
        "Valor",
        max_digits=10,
        decimal_places=2,
    )
    installments = models.PositiveIntegerField(
        "Parcelas", default=1, help_text="1 a 3 parcelas"
    )
    description = models.CharField(
        "Descrição",
        max_length=200,
    )

    # ======================================================================
    # DADOS DO CLIENTE (Quem deve pagar - Preenchido na criação)
    # ======================================================================
    customer_name = models.CharField("Nome do Cliente", max_length=200)
    customer_phone = models.CharField("Telefone", max_length=20, blank=True)
    customer_email = models.EmailField("E-mail", blank=True)

    # ======================================================================
    # DADOS DO PAGADOR (Quem realmente pagou - Preenchido via Webhook)
    # ======================================================================
    payer_name = models.CharField("Nome do Pagador", max_length=200, blank=True)
    payer_document = models.CharField("CPF/CNPJ do Pagador", max_length=20, blank=True)
    payer_email = models.EmailField("E-mail do Pagador", blank=True)
    payer_phone = models.CharField("Telefone do Pagador", max_length=20, blank=True)

    # Endereço do Pagador (Novo)
    payer_address_zip = models.CharField("CEP do Pagador", max_length=10, blank=True)
    payer_address_street = models.CharField(
        "Rua do Pagador", max_length=200, blank=True
    )
    payer_address_number = models.CharField("Número", max_length=20, blank=True)
    payer_address_complement = models.CharField(
        "Complemento", max_length=100, blank=True
    )
    payer_address_neighborhood = models.CharField("Bairro", max_length=100, blank=True)
    payer_address_city = models.CharField("Cidade", max_length=100, blank=True)
    payer_address_state = models.CharField("UF", max_length=2, blank=True)

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

    @db_transaction.atomic
    def mark_as_paid(self, webhook_data=None):
        """Marca como pago com bloqueio pessimista para evitar double-processing."""
        # Seleciona com lock
        link = self.__class__.objects.select_for_update().get(pk=self.pk)
        if link.status == self.Status.PAID:
            return # Já processado

        link.status = self.Status.PAID
        link.paid_at = timezone.now()

        if webhook_data:
            self.webhook_data = webhook_data

            # Lógica de extração segura
            try:
                data = webhook_data.get("data", {})
                customer = data.get("customer", {})

                if customer:
                    link.payer_name = customer.get("name", "")[:200]
                    link.payer_email = customer.get("email", "")
                    link.payer_document = customer.get("document", "")[:20]

                    # Extração de telefone
                    phones = customer.get("phones", {})
                    mobile = phones.get("mobile_phone")
                    if mobile:
                        country = mobile.get("country_code", "")
                        area = mobile.get("area_code", "")
                        number = mobile.get("number", "")
                        link.payer_phone = f"{country}{area}{number}"[:20]
                    else:
                        home = phones.get("home_phone")
                        if home:
                            country = home.get("country_code", "")
                            area = home.get("area_code", "")
                            number = home.get("number", "")
                            link.payer_phone = f"{country}{area}{number}"[:20]

                    # Extração de Endereço (NOVO)
                    address = customer.get("address", {})
                    if address:
                        link.payer_address_zip = address.get("zip_code", "")[:10]
                        link.payer_address_street = address.get("street", "")[:200]
                        link.payer_address_number = address.get("number", "")[:20]
                        link.payer_address_complement = address.get("complement", "")[:100]
                        link.payer_address_neighborhood = address.get("neighborhood", "")[:100]
                        link.payer_address_city = address.get("city", "")[:100]
                        link.payer_address_state = address.get("state", "")[:2]
            except Exception:
                pass

        link.save()

        # Atualiza pedido vinculado com lock se possível
        if link.order:
            from apps.orders.models import PaymentStatus, Order
            order = Order.objects.select_for_update().get(id=link.order_id)
            order.payment_status = PaymentStatus.PAID
            order.save(update_fields=["payment_status", "updated_at"])

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
