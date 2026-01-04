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

    # WhatsApp
    whatsapp_enabled = models.BooleanField("WhatsApp Ativo", default=True)

    # Mensagens customizáveis
    msg_order_created = models.TextField(
        "Mensagem: Pedido Criado",
        help_text="Placeholders disponíveis: {nome}, {codigo}, {valor}",
        default=(
            "Olá {nome}! 🎉\n\n"
            "Seu pedido *{codigo}* foi recebido!\n"
            "Valor: R$ {valor}\n\n"
            "Obrigado pela preferência!"
        ),
    )

    msg_order_shipped = models.TextField(
        "Mensagem: Pedido Enviado",
        help_text="Placeholders disponíveis: {nome}, {codigo}. Rastreio é adicionado automaticamente.",
        default=(
            "Olá {nome}! 📦\n\n"
            "Seu pedido *{codigo}* foi enviado!\n"
        ),
    )

    msg_order_delivered = models.TextField(
        "Mensagem: Pedido Entregue",
        help_text="Placeholders disponíveis: {nome}, {codigo}",
        default=(
            "Olá {nome}! ✅\n\n"
            "Seu pedido *{codigo}* foi entregue!\n\n"
            "Obrigado por comprar conosco!"
        ),
    )

    msg_order_ready_for_pickup = models.TextField(
        "Mensagem: Pronto para Retirada",
        help_text="Placeholders disponíveis: {nome}, {codigo}, {valor}",
        default=(
            "Olá {nome}! 🏬\n\n"
            "Seu pedido *{codigo}* está pronto para retirada!\n"
            "Valor: R$ {valor}\n\n"
            "Aguardamos você em nossa loja! 😊"
        ),
    )

    class Meta:
        verbose_name = "Configuração"
        verbose_name_plural = "Configurações"
        ordering = ["tenant"]

    def __str__(self):
        return f"Configurações - {self.tenant.name}"


@receiver(post_save, sender=Tenant)
def create_tenant_settings(sender, instance, created, **kwargs):
    """Garante que todo tenant tenha configurações."""
    if created:
        TenantSettings.objects.create(tenant=instance)
