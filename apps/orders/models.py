"""
Models do app orders - MVP Bibelo.
"""

import random
import string

from django.db import models

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


class DeliveryType(models.TextChoices):
    DELIVERY = "delivery", "Entrega"
    PICKUP = "pickup", "Retirada na loja"


class Customer(TenantModel):
    objects = TenantManager()

    name = models.CharField("Nome", max_length=200)
    phone = models.CharField("Telefone", max_length=20)
    phone_normalized = models.CharField(
        "Telefone Normalizado", max_length=20, db_index=True, editable=False
    )

    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["tenant", "phone_normalized"]),
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

    delivery_type = models.CharField(
        "Tipo de entrega",
        max_length=20,
        choices=DeliveryType.choices,
        default=DeliveryType.DELIVERY,
    )

    delivery_address = models.TextField("Endereço de Entrega", blank=True)
    notes = models.TextField("Observações", blank=True)

    class Meta:
        verbose_name = "Pedido"
        verbose_name_plural = "Pedidos"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "created_at"]),
            models.Index(fields=["tenant", "order_status"]),
            models.Index(fields=["code"]),
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

    @property
    def can_be_cancelled(self):
        return (
            self.order_status not in [OrderStatus.COMPLETED, OrderStatus.CANCELLED]
            and self.delivery_status != DeliveryStatus.DELIVERED
        )

    @property
    def status_display(self):
        if self.order_status == OrderStatus.CANCELLED:
            return "Cancelado"
        if self.delivery_status == DeliveryStatus.DELIVERED:
            return "Entregue"
        if self.delivery_status == DeliveryStatus.SHIPPED:
            return "Enviado"
        if self.payment_status == PaymentStatus.PAID:
            return "Pago"
        return "Pendente"
