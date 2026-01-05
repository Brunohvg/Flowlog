"""
Models do app orders - Flowlog.
Sistema completo de gestão de pedidos.
"""

import random
import string
from datetime import timedelta

from django.db import models
from django.utils import timezone

from apps.core.managers import TenantManager
from apps.core.models import TenantModel


class OrderStatus(models.TextChoices):
    PENDING = "pending", "Pendente"
    CONFIRMED = "confirmed", "Confirmado"
    COMPLETED = "completed", "Concluído"
    CANCELLED = "cancelled", "Cancelado"
    RETURNED = "returned", "Devolvido"


class PaymentStatus(models.TextChoices):
    PENDING = "pending", "Pendente"
    PAID = "paid", "Pago"
    REFUNDED = "refunded", "Reembolsado"


class DeliveryStatus(models.TextChoices):
    PENDING = "pending", "Pendente"
    SHIPPED = "shipped", "Enviado"
    DELIVERED = "delivered", "Entregue"
    READY_FOR_PICKUP = "ready_for_pickup", "Pronto para retirada"
    PICKED_UP = "picked_up", "Retirado"
    FAILED_ATTEMPT = "failed_attempt", "Tentativa de entrega"
    EXPIRED = "expired", "Expirado"


class DeliveryType(models.TextChoices):
    """
    Tipos de entrega disponíveis.
    """
    PICKUP = "pickup", "Retirada na Loja"
    MOTOBOY = "motoboy", "Motoboy"
    SEDEX = "sedex", "SEDEX"
    PAC = "pac", "PAC"

    @classmethod
    def requires_address(cls, delivery_type):
        return delivery_type != cls.PICKUP

    @classmethod
    def requires_tracking(cls, delivery_type):
        return delivery_type in [cls.SEDEX, cls.PAC]

    @classmethod
    def is_correios(cls, delivery_type):
        return delivery_type in [cls.SEDEX, cls.PAC]

    @classmethod
    def is_delivery(cls, delivery_type):
        return delivery_type != cls.PICKUP


class Customer(TenantModel):
    """Cliente do sistema."""
    objects = TenantManager()

    name = models.CharField("Nome", max_length=200)
    phone = models.CharField("Telefone", max_length=20)
    phone_normalized = models.CharField(
        "Telefone Normalizado", max_length=20, db_index=True, editable=False
    )
    cpf = models.CharField(
        "CPF", max_length=14, blank=True,
        help_text="CPF do cliente (usado para acompanhamento)"
    )
    cpf_normalized = models.CharField(
        "CPF Normalizado", max_length=11, blank=True, db_index=True, editable=False
    )
    email = models.EmailField("E-mail", blank=True)
    notes = models.TextField("Observações internas", blank=True, help_text="Notas visíveis apenas para vendedores")
    is_blocked = models.BooleanField("Bloqueado", default=False, help_text="Impede novos pedidos")

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
    
    @property
    def last_4_phone(self):
        """Últimos 4 dígitos do telefone para verificação."""
        return self.phone_normalized[-4:] if len(self.phone_normalized) >= 4 else self.phone_normalized
    
    @property
    def last_4_cpf(self):
        """Últimos 4 dígitos do CPF para verificação."""
        return self.cpf_normalized[-4:] if len(self.cpf_normalized) >= 4 else ""


class Order(TenantModel):
    """Pedido de venda."""
    objects = TenantManager()

    # Identificação
    code = models.CharField("Código", max_length=20, unique=True, editable=False)

    # Relacionamentos
    customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT,
        related_name="orders", verbose_name="Cliente",
    )
    seller = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT,
        related_name="orders", verbose_name="Vendedor",
    )

    # Valores
    total_value = models.DecimalField("Valor Total", max_digits=10, decimal_places=2)

    # Status
    order_status = models.CharField(
        "Status do Pedido", max_length=20,
        choices=OrderStatus.choices, default=OrderStatus.PENDING,
    )
    payment_status = models.CharField(
        "Status do Pagamento", max_length=20,
        choices=PaymentStatus.choices, default=PaymentStatus.PENDING,
    )
    delivery_status = models.CharField(
        "Status da Entrega", max_length=20,
        choices=DeliveryStatus.choices, default=DeliveryStatus.PENDING,
    )

    # Tipo de entrega
    delivery_type = models.CharField(
        "Tipo de Entrega", max_length=20,
        choices=DeliveryType.choices, default=DeliveryType.MOTOBOY,
    )

    # Entrega
    delivery_address = models.TextField("Endereço de Entrega", blank=True)
    tracking_code = models.CharField("Código de Rastreio", max_length=50, blank=True)

    # Timestamps de entrega
    shipped_at = models.DateTimeField("Enviado em", null=True, blank=True)
    delivered_at = models.DateTimeField("Entregue em", null=True, blank=True)
    expires_at = models.DateTimeField("Expira em", null=True, blank=True, help_text="Para retiradas não realizadas")

    # Cancelamento/Devolução
    cancel_reason = models.TextField("Motivo do cancelamento", blank=True)
    cancelled_at = models.DateTimeField("Cancelado em", null=True, blank=True)
    return_reason = models.TextField("Motivo da devolução", blank=True)
    returned_at = models.DateTimeField("Devolvido em", null=True, blank=True)

    # Observações
    notes = models.TextField("Observações", blank=True)
    internal_notes = models.TextField("Notas internas", blank=True, help_text="Visível apenas para vendedores")
    
    # Controle
    is_priority = models.BooleanField("Prioritário", default=False)
    delivery_attempts = models.PositiveSmallIntegerField("Tentativas de entrega", default=0)

    class Meta:
        verbose_name = "Pedido"
        verbose_name_plural = "Pedidos"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "created_at"]),
            models.Index(fields=["tenant", "order_status"]),
            models.Index(fields=["tenant", "delivery_type"]),
            models.Index(fields=["tenant", "delivery_status"]),
            models.Index(fields=["code"]),
            models.Index(fields=["tracking_code"]),
            models.Index(fields=["expires_at"]),
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
    def is_active(self):
        """Pedido ainda está ativo (não finalizado)."""
        return self.order_status not in [
            OrderStatus.COMPLETED, OrderStatus.CANCELLED, OrderStatus.RETURNED
        ]

    @property
    def is_finalized(self):
        """Pedido foi finalizado (concluído, cancelado ou devolvido)."""
        return not self.is_active

    @property
    def can_be_cancelled(self):
        """Pode ser cancelado (antes da entrega/retirada)."""
        return self.order_status not in [OrderStatus.CANCELLED, OrderStatus.RETURNED]

    @property
    def can_be_returned(self):
        """Pode ser devolvido (após entrega/retirada)."""
        return (
            self.order_status == OrderStatus.COMPLETED
            and self.delivery_status in [DeliveryStatus.DELIVERED, DeliveryStatus.PICKED_UP]
        )

    @property
    def can_change_delivery_type(self):
        """Pode mudar tipo de entrega."""
        return (
            self.is_active
            and self.delivery_status in [DeliveryStatus.PENDING, DeliveryStatus.READY_FOR_PICKUP]
        )

    @property
    def can_be_shipped(self):
        """Pode ser enviado."""
        return (
            DeliveryType.is_delivery(self.delivery_type)
            and self.delivery_status == DeliveryStatus.PENDING
            and self.order_status not in [OrderStatus.CANCELLED, OrderStatus.RETURNED]
        )

    @property
    def can_be_delivered(self):
        """Pode ser marcado como entregue."""
        return (
            DeliveryType.is_delivery(self.delivery_type)
            and self.delivery_status in [DeliveryStatus.SHIPPED, DeliveryStatus.FAILED_ATTEMPT]
        )

    @property
    def can_be_ready_for_pickup(self):
        """Pode ser liberado para retirada."""
        return (
            self.delivery_type == DeliveryType.PICKUP
            and self.delivery_status == DeliveryStatus.PENDING
            and self.order_status not in [OrderStatus.CANCELLED, OrderStatus.RETURNED]
        )

    @property
    def can_be_picked_up(self):
        """Pode ser marcado como retirado."""
        return (
            self.delivery_type == DeliveryType.PICKUP
            and self.delivery_status == DeliveryStatus.READY_FOR_PICKUP
        )

    @property
    def can_mark_failed_attempt(self):
        """Pode marcar tentativa de entrega falha."""
        return (
            DeliveryType.is_delivery(self.delivery_type)
            and self.delivery_status == DeliveryStatus.SHIPPED
        )

    @property
    def can_resend_notification(self):
        """Pode reenviar notificação WhatsApp."""
        return self.order_status not in [OrderStatus.CANCELLED, OrderStatus.RETURNED]

    @property
    def requires_tracking(self):
        return DeliveryType.requires_tracking(self.delivery_type)

    @property
    def is_correios(self):
        return DeliveryType.is_correios(self.delivery_type)

    @property
    def is_pickup(self):
        return self.delivery_type == DeliveryType.PICKUP

    @property
    def is_expired(self):
        """Verifica se expirou (para retiradas)."""
        if self.expires_at and self.delivery_status == DeliveryStatus.READY_FOR_PICKUP:
            return timezone.now() > self.expires_at
        return False

    @property
    def hours_until_expiry(self):
        """Horas até expirar."""
        if self.expires_at and self.delivery_status == DeliveryStatus.READY_FOR_PICKUP:
            delta = self.expires_at - timezone.now()
            if delta.total_seconds() > 0:
                return int(delta.total_seconds() / 3600)
        return None

    @property
    def tracking_url(self):
        if self.tracking_code and self.is_correios:
            return f"https://rastreamento.correios.com.br/app/index.php?objetos={self.tracking_code}"
        return None

    @property
    def status_display(self):
        """Status principal para exibição."""
        if self.order_status == OrderStatus.CANCELLED:
            return "Cancelado"
        if self.order_status == OrderStatus.RETURNED:
            return "Devolvido"
        if self.delivery_status == DeliveryStatus.EXPIRED:
            return "Expirado"
        if self.delivery_status == DeliveryStatus.PICKED_UP:
            return "Retirado"
        if self.delivery_status == DeliveryStatus.DELIVERED:
            return "Entregue"
        if self.delivery_status == DeliveryStatus.FAILED_ATTEMPT:
            return f"Tentativa {self.delivery_attempts}"
        if self.delivery_status == DeliveryStatus.SHIPPED:
            return "Enviado"
        if self.delivery_status == DeliveryStatus.READY_FOR_PICKUP:
            return "Pronto para Retirada"
        if self.payment_status == PaymentStatus.PAID:
            return "Pago"
        return "Pendente"

    @property
    def status_color(self):
        """Cor do status para badges."""
        colors = {
            "Cancelado": "red",
            "Devolvido": "red",
            "Expirado": "red",
            "Retirado": "emerald",
            "Entregue": "emerald",
            "Enviado": "blue",
            "Pronto para Retirada": "purple",
            "Pago": "emerald",
            "Pendente": "amber",
        }
        status = self.status_display
        if status.startswith("Tentativa"):
            return "amber"
        return colors.get(status, "slate")


class OrderActivity(models.Model):
    """Histórico de atividades do pedido."""
    
    class ActivityType(models.TextChoices):
        CREATED = "created", "Pedido criado"
        STATUS_CHANGED = "status_changed", "Status alterado"
        PAYMENT_RECEIVED = "payment_received", "Pagamento recebido"
        SHIPPED = "shipped", "Enviado"
        DELIVERED = "delivered", "Entregue"
        READY_PICKUP = "ready_pickup", "Pronto para retirada"
        PICKED_UP = "picked_up", "Retirado"
        FAILED_ATTEMPT = "failed_attempt", "Tentativa de entrega"
        CANCELLED = "cancelled", "Cancelado"
        RETURNED = "returned", "Devolvido"
        REFUNDED = "refunded", "Reembolsado"
        DELIVERY_TYPE_CHANGED = "delivery_type_changed", "Tipo de entrega alterado"
        NOTE_ADDED = "note_added", "Nota adicionada"
        NOTIFICATION_SENT = "notification_sent", "Notificação enviada"
        EXPIRED = "expired", "Expirado"
        EDITED = "edited", "Editado"
    
    order = models.ForeignKey(
        Order, on_delete=models.CASCADE,
        related_name="activities", verbose_name="Pedido"
    )
    activity_type = models.CharField(
        "Tipo", max_length=30, choices=ActivityType.choices
    )
    description = models.TextField("Descrição")
    user = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="Usuário"
    )
    metadata = models.JSONField("Metadados", default=dict, blank=True)
    created_at = models.DateTimeField("Criado em", auto_now_add=True)

    class Meta:
        verbose_name = "Atividade"
        verbose_name_plural = "Atividades"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["order", "created_at"]),
        ]

    def __str__(self):
        return f"{self.order.code} - {self.get_activity_type_display()}"

    @classmethod
    def log(cls, order, activity_type, description, user=None, **metadata):
        """Cria um registro de atividade."""
        return cls.objects.create(
            order=order,
            activity_type=activity_type,
            description=description,
            user=user,
            metadata=metadata,
        )
