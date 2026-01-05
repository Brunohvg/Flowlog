"""
Models do app tenants.
"""

from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.core.models import BaseModel


class Tenant(BaseModel):
    """Empresa/Organização no sistema."""

    name = models.CharField("Nome", max_length=200)
    slug = models.SlugField("Slug", unique=True)
    contact_email = models.EmailField("E-mail de contato")
    contact_phone = models.CharField("Telefone de contato", max_length=20, blank=True)
    address = models.TextField("Endereço", blank=True, help_text="Endereço para retiradas")
    is_active = models.BooleanField("Ativo", default=True)

    class Meta:
        verbose_name = "Empresa"
        verbose_name_plural = "Empresas"
        ordering = ["name"]

    def __str__(self):
        return self.name


class TenantSettings(BaseModel):
    """Configurações do tenant (WhatsApp, mensagens, etc)."""

    tenant = models.OneToOneField(
        Tenant,
        on_delete=models.CASCADE,
        related_name="settings",
    )

    # ==================== EVOLUTION API ====================
    whatsapp_enabled = models.BooleanField("WhatsApp Ativo", default=False)
    evolution_api_url = models.URLField(
        "URL da Evolution API",
        blank=True,
        help_text="Ex: https://api.evolution.com.br",
    )
    evolution_api_key = models.CharField(
        "API Key da Evolution",
        max_length=200,
        blank=True,
    )
    evolution_instance = models.CharField(
        "Nome da Instância",
        max_length=100,
        blank=True,
        help_text="Nome da instância criada na Evolution API",
    )
    whatsapp_number = models.CharField(
        "Número do WhatsApp",
        max_length=20,
        blank=True,
        help_text="Número conectado (apenas visualização)",
    )
    whatsapp_connected = models.BooleanField(
        "WhatsApp Conectado",
        default=False,
        editable=False,
    )

    # ==================== MENSAGENS - PEDIDO ====================
    msg_order_created = models.TextField(
        "Mensagem: Pedido Criado",
        help_text="Placeholders: {nome}, {codigo}, {valor}, {loja}",
        default=(
            "Olá {nome}! 🎉\n\n"
            "Seu pedido *{codigo}* foi recebido!\n"
            "Valor: R$ {valor}\n\n"
            "Acompanhe seu pedido em:\n{link_rastreio}\n\n"
            "Obrigado pela preferência!\n"
            "_{loja}_"
        ),
    )

    msg_order_confirmed = models.TextField(
        "Mensagem: Pedido Confirmado",
        help_text="Placeholders: {nome}, {codigo}, {loja}",
        default=(
            "Olá {nome}! ✅\n\n"
            "Seu pedido *{codigo}* foi confirmado e está sendo preparado!\n\n"
            "_{loja}_"
        ),
    )

    # ==================== MENSAGENS - PAGAMENTO ====================
    msg_payment_received = models.TextField(
        "Mensagem: Pagamento Recebido",
        help_text="Placeholders: {nome}, {codigo}, {valor}, {loja}",
        default=(
            "Olá {nome}! 💰\n\n"
            "Recebemos o pagamento do seu pedido *{codigo}*!\n"
            "Valor: R$ {valor}\n\n"
            "Obrigado!\n"
            "_{loja}_"
        ),
    )

    msg_payment_refunded = models.TextField(
        "Mensagem: Pagamento Estornado",
        help_text="Placeholders: {nome}, {codigo}, {valor}, {loja}",
        default=(
            "Olá {nome}!\n\n"
            "O valor de R$ {valor} referente ao pedido *{codigo}* foi estornado.\n\n"
            "Em caso de dúvidas, entre em contato.\n"
            "_{loja}_"
        ),
    )

    # ==================== MENSAGENS - ENTREGA ====================
    msg_order_shipped = models.TextField(
        "Mensagem: Pedido Enviado",
        help_text="Placeholders: {nome}, {codigo}, {rastreio}, {link_rastreio}, {loja}",
        default=(
            "Olá {nome}! 📦\n\n"
            "Seu pedido *{codigo}* foi enviado!\n\n"
            "{rastreio_info}"
            "Acompanhe em:\n{link_rastreio}\n\n"
            "_{loja}_"
        ),
    )

    msg_order_delivered = models.TextField(
        "Mensagem: Pedido Entregue",
        help_text="Placeholders: {nome}, {codigo}, {loja}",
        default=(
            "Olá {nome}! ✅\n\n"
            "Seu pedido *{codigo}* foi entregue!\n\n"
            "Obrigado por comprar conosco! 😊\n"
            "_{loja}_"
        ),
    )

    msg_delivery_failed = models.TextField(
        "Mensagem: Tentativa de Entrega Falha",
        help_text="Placeholders: {nome}, {codigo}, {tentativa}, {loja}",
        default=(
            "Olá {nome}! ⚠️\n\n"
            "Tentamos entregar seu pedido *{codigo}* mas não conseguimos.\n"
            "Tentativa: {tentativa}\n\n"
            "Por favor, verifique o endereço ou entre em contato.\n"
            "_{loja}_"
        ),
    )

    # ==================== MENSAGENS - RETIRADA ====================
    msg_order_ready_for_pickup = models.TextField(
        "Mensagem: Pronto para Retirada",
        help_text="Placeholders: {nome}, {codigo}, {valor}, {endereco}, {loja}",
        default=(
            "Olá {nome}! 🏬\n\n"
            "Seu pedido *{codigo}* está pronto para retirada!\n"
            "Valor: R$ {valor}\n\n"
            "📍 Retire em:\n{endereco}\n\n"
            "⏰ Prazo: 48 horas\n\n"
            "Aguardamos você!\n"
            "_{loja}_"
        ),
    )

    msg_order_picked_up = models.TextField(
        "Mensagem: Pedido Retirado",
        help_text="Placeholders: {nome}, {codigo}, {loja}",
        default=(
            "Olá {nome}! ✅\n\n"
            "Seu pedido *{codigo}* foi retirado com sucesso!\n\n"
            "Obrigado pela preferência! 😊\n"
            "_{loja}_"
        ),
    )

    msg_order_expired = models.TextField(
        "Mensagem: Pedido Expirado (Retirada)",
        help_text="Placeholders: {nome}, {codigo}, {loja}",
        default=(
            "Olá {nome}! ⚠️\n\n"
            "Infelizmente o prazo para retirada do pedido *{codigo}* expirou.\n\n"
            "Entre em contato para verificar as opções disponíveis.\n"
            "_{loja}_"
        ),
    )

    # ==================== MENSAGENS - CANCELAMENTO ====================
    msg_order_cancelled = models.TextField(
        "Mensagem: Pedido Cancelado",
        help_text="Placeholders: {nome}, {codigo}, {motivo}, {loja}",
        default=(
            "Olá {nome}!\n\n"
            "Seu pedido *{codigo}* foi cancelado.\n"
            "{motivo_info}\n"
            "Em caso de dúvidas, entre em contato.\n"
            "_{loja}_"
        ),
    )

    msg_order_returned = models.TextField(
        "Mensagem: Pedido Devolvido",
        help_text="Placeholders: {nome}, {codigo}, {motivo}, {loja}",
        default=(
            "Olá {nome}!\n\n"
            "Registramos a devolução do pedido *{codigo}*.\n"
            "{motivo_info}\n"
            "Obrigado pelo contato.\n"
            "_{loja}_"
        ),
    )

    class Meta:
        verbose_name = "Configuração"
        verbose_name_plural = "Configurações"
        ordering = ["tenant"]

    def __str__(self):
        return f"Configurações - {self.tenant.name}"
    
    @property
    def is_whatsapp_configured(self):
        """Verifica se WhatsApp está configurado."""
        return bool(
            self.whatsapp_enabled
            and self.evolution_api_url
            and self.evolution_api_key
            and self.evolution_instance
        )


@receiver(post_save, sender=Tenant)
def create_tenant_settings(sender, instance, created, **kwargs):
    """Garante que todo tenant tenha configurações."""
    if created:
        TenantSettings.objects.create(tenant=instance)
