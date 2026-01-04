"""
Models do app orders - Flowlog.
"""

import random
import string

from django.db import models
from django.utils import timezone

from apps.core.managers import TenantManager
from apps.core.models import TenantModel


class OrderStatus(models.TextChoices):
    PENDING = "pending", "Pendente"
    CONFIRMED = "confirmed", "Confirmado"
    COMPLETED = "completed", "Concluído"
    CANCELLED = "cancelled", "Cancelado"


class PaymentStatus(models.TextChoices):
    PENDING = "pending", "Pendente"
    PAID = "paid", "Pago"


class DeliveryStatus(models.TextChoices):
    PENDING = "pending", "Pendente"
    SHIPPED = "shipped", "Enviado"
    DELIVERED = "delivered", "Entregue"
    READY_FOR_PICKUP = "ready_for_pickup", "Pronto para retirada"
    PICKED_UP = "picked_up", "Retirado"


class DeliveryType(models.TextChoices):
    """
    Tipos de entrega disponíveis.
    - PICKUP: Retirada na loja (sem endereço, sem rastreio)
    - MOTOBOY: Entrega via motoboy (com endereço, rastreio opcional)
    - SEDEX: Correios SEDEX (com endereço, rastreio obrigatório)
    - PAC: Correios PAC (com endereço, rastreio obrigatório)
    """
    PICKUP = "pickup", "Retirada na Loja"
    MOTOBOY = "motoboy", "Motoboy"
    SEDEX = "sedex", "SEDEX"
    PAC = "pac", "PAC"

    @classmethod
    def requires_address(cls, delivery_type):
        """Retorna True se o tipo exige endereço."""
        return delivery_type != cls.PICKUP

    @classmethod
    def requires_tracking(cls, delivery_type):
        """Retorna True se o tipo exige código de rastreio."""
        return delivery_type in [cls.SEDEX, cls.PAC]

    @classmethod
    def is_correios(cls, delivery_type):
        """Retorna True se é entrega via Correios."""
        return delivery_type in [cls.SEDEX, cls.PAC]

    @classmethod
    def is_delivery(cls, delivery_type):
        """Retorna True se é qualquer tipo de entrega (não retirada)."""
        return delivery_type != cls.PICKUP


class Customer(TenantModel):
    objects = TenantManager()

    name = models.CharField("Nome", max_length=200)
    phone = models.CharField("Telefone", max_length=20)
    phone_normalized = models.CharField(
        "Telefone Normalizado", max_length=20, db_index=True, editable=False
    )
    cpf = models.CharField(
        "CPF",
        max_length=14,
        blank=True,
        help_text="CPF do cliente (usado para acompanhamento)"
    )
    cpf_normalized = models.CharField(
        "CPF Normalizado",
        max_length=11,
        blank=True,
        db_index=True,
        editable=False
    )

    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["tenant", "phone_normalized"]),
            models.Index(fields=["tenant", "cpf_normalized"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "phone_normalized"],
                name="unique_customer_phone_per_tenant",
            )
        ]

    def __str__(self):
        return f"{self.name} - {self.phone}"

    def save(self, *args, **kwargs):
        self.phone_normalized = "".join(filter(str.isdigit, self.phone))
        if self.cpf:
            self.cpf_normalized = "".join(filter(str.isdigit, self.cpf))
        super().save(*args, **kwargs)


class Order(TenantModel):
    objects = TenantManager()

    code = models.CharField("Código", max_length=20, unique=True, editable=False)

    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name="orders",
        verbose_name="Cliente",
    )
    seller = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="orders",
        verbose_name="Vendedor",
    )

    total_value = models.DecimalField("Valor Total", max_digits=10, decimal_places=2)

    # Status
    order_status = models.CharField(
        "Status do Pedido",
        max_length=20,
        choices=OrderStatus.choices,
        default=OrderStatus.PENDING,
    )
    payment_status = models.CharField(
        "Status do Pagamento",
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
    )
    delivery_status = models.CharField(
        "Status da Entrega",
        max_length=20,
        choices=DeliveryStatus.choices,
        default=DeliveryStatus.PENDING,
    )

    # Tipo de entrega (pickup, motoboy, sedex, pac)
    delivery_type = models.CharField(
        "Tipo de Entrega",
        max_length=20,
        choices=DeliveryType.choices,
        default=DeliveryType.MOTOBOY,
    )

    # Endereço e rastreio
    delivery_address = models.TextField("Endereço de Entrega", blank=True)
    tracking_code = models.CharField(
        "Código de Rastreio",
        max_length=50,
        blank=True,
        help_text="Obrigatório para SEDEX e PAC"
    )

    # Timestamps de entrega
    shipped_at = models.DateTimeField("Enviado em", null=True, blank=True)
    delivered_at = models.DateTimeField("Entregue em", null=True, blank=True)

    # Observações
    notes = models.TextField("Observações", blank=True)

    class Meta:
        verbose_name = "Pedido"
        verbose_name_plural = "Pedidos"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "created_at"]),
            models.Index(fields=["tenant", "order_status"]),
            models.Index(fields=["tenant", "delivery_type"]),
            models.Index(fields=["code"]),
            models.Index(fields=["tracking_code"]),
        ]

    def __str__(self):
        return f"{self.code} - {self.customer.name}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = self._generate_code()
        super().save(*args, **kwargs)

    def _generate_code(self):
        chars = string.ascii_uppercase + string.digits
        while True:
            random_part = "".join(random.choices(chars, k=5))
            code = f"PED-{random_part}"
            if not self.__class__._default_manager.filter(code=code).exists():
                return code

    # ==================== PROPRIEDADES ====================

    @property
    def can_be_cancelled(self):
        """Verifica se o pedido pode ser cancelado."""
        return (
            self.order_status not in [OrderStatus.COMPLETED, OrderStatus.CANCELLED]
            and self.delivery_status not in [DeliveryStatus.DELIVERED, DeliveryStatus.PICKED_UP]
        )

    @property
    def can_be_shipped(self):
        """Verifica se o pedido pode ser enviado."""
        return (
            DeliveryType.is_delivery(self.delivery_type)
            and self.delivery_status == DeliveryStatus.PENDING
            and self.order_status != OrderStatus.CANCELLED
        )

    @property
    def can_be_delivered(self):
        """Verifica se o pedido pode ser marcado como entregue."""
        return (
            DeliveryType.is_delivery(self.delivery_type)
            and self.delivery_status == DeliveryStatus.SHIPPED
        )

    @property
    def can_be_ready_for_pickup(self):
        """Verifica se pode ser liberado para retirada."""
        return (
            self.delivery_type == DeliveryType.PICKUP
            and self.delivery_status == DeliveryStatus.PENDING
        )

    @property
    def can_be_picked_up(self):
        """Verifica se pode ser marcado como retirado."""
        return (
            self.delivery_type == DeliveryType.PICKUP
            and self.delivery_status == DeliveryStatus.READY_FOR_PICKUP
        )

    @property
    def requires_tracking(self):
        """Verifica se exige código de rastreio."""
        return DeliveryType.requires_tracking(self.delivery_type)

    @property
    def is_correios(self):
        """Verifica se é entrega via Correios."""
        return DeliveryType.is_correios(self.delivery_type)

    @property
    def is_pickup(self):
        """Verifica se é retirada na loja."""
        return self.delivery_type == DeliveryType.PICKUP

    @property
    def tracking_url(self):
        """URL de rastreio dos Correios."""
        if self.tracking_code and self.is_correios:
            return f"https://rastreamento.correios.com.br/app/index.php?objetos={self.tracking_code}"
        return None

    @property
    def status_display(self):
        """Retorna status principal para exibição."""
        if self.order_status == OrderStatus.CANCELLED:
            return "Cancelado"
        if self.delivery_status == DeliveryStatus.PICKED_UP:
            return "Retirado"
        if self.delivery_status == DeliveryStatus.DELIVERED:
            return "Entregue"
        if self.delivery_status == DeliveryStatus.SHIPPED:
            return "Enviado"
        if self.delivery_status == DeliveryStatus.READY_FOR_PICKUP:
            return "Pronto para Retirada"
        if self.payment_status == PaymentStatus.PAID:
            return "Pago"
        return "Pendente"

    @property
    def delivery_type_display_short(self):
        """Nome curto do tipo de entrega para badges."""
        labels = {
            DeliveryType.PICKUP: "Retirada",
            DeliveryType.MOTOBOY: "Motoboy",
            DeliveryType.SEDEX: "SEDEX",
            DeliveryType.PAC: "PAC",
        }
        return labels.get(self.delivery_type, self.delivery_type)
