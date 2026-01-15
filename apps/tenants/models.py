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
    """Configurações do tenant (Pagar.me, WhatsApp, mensagens, etc)."""

    tenant = models.OneToOneField(
        Tenant,
        on_delete=models.CASCADE,
        related_name="settings",
    )

    # ==================== PAGAR.ME ====================
    pagarme_enabled = models.BooleanField(
        "Pagar.me Ativo",
        default=False,
    )
    pagarme_api_key = models.CharField(
        "Secret Key",
        max_length=200,
        blank=True,
        help_text="Chave secreta do Pagar.me (sk_xxx)",
    )
    pagarme_max_installments = models.PositiveIntegerField(
        "Máximo de Parcelas",
        default=3,
        help_text="1 a 3 parcelas",
    )
    pagarme_pix_enabled = models.BooleanField(
        "PIX Habilitado",
        default=False,
        help_text="Habilitar PIX como forma de pagamento (requer liberação na Pagar.me)",
    )

    # ==================== CORREIOS ====================
    # API usa Basic Auth (usuario:codigo_acesso) para obter token JWT
    # Token é cacheado até expiração (campo expiraEm na resposta)
    correios_enabled = models.BooleanField("Correios Ativo", default=False)
    correios_usuario = models.CharField(
        "Usuário (Meu Correios)",
        max_length=50,
        blank=True,
        help_text="Seu usuário do portal Meu Correios",
    )
    correios_codigo_acesso = models.CharField(
        "Código de Acesso",
        max_length=100,
        blank=True,
        help_text="Código de acesso gerado no portal Meu Correios",
    )
    correios_contrato = models.CharField(
        "Número do Contrato",
        max_length=20,
        blank=True,
        help_text="Opcional: para APIs que exigem contrato",
    )
    correios_cartao_postagem = models.CharField(
        "Cartão de Postagem",
        max_length=20,
        blank=True,
        help_text="Opcional: para APIs que exigem cartão",
    )
    # Token cacheado (preenchido automaticamente)
    correios_token = models.TextField(
        "Token (automático)",
        blank=True,
        editable=False,
    )
    correios_token_expira = models.DateTimeField(
        "Expiração do Token",
        null=True,
        blank=True,
        editable=False,
    )

    # ==================== MANDAÊ ====================
    mandae_enabled = models.BooleanField("Mandaê Ativo", default=False)
    mandae_api_url = models.URLField(
        "URL da API Mandaê",
        blank=True,
        default="https://api.mandae.com.br/v2/",
    )
    mandae_token = models.CharField(
        "Token Mandaê",
        max_length=100,
        blank=True,
        help_text="Token de autenticação da API",
    )
    mandae_customer_id = models.CharField(
        "Customer ID Mandaê",
        max_length=100,
        blank=True,
        help_text="ID do cliente na Mandaê",
    )
    mandae_tracking_prefix = models.CharField(
        "Prefixo de Rastreio",
        max_length=10,
        blank=True,
        help_text="Ex: ATSNR",
    )
    mandae_webhook_secret = models.CharField(
        "Webhook Secret",
        max_length=100,
        blank=True,
        help_text="Chave para validar webhooks recebidos",
    )

    # ==================== MOTOBOY / FRETE ====================
    store_cep = models.CharField(
        "CEP da Loja",
        max_length=9,
        blank=True,
        help_text="CEP de origem para cálculos de frete",
    )
    store_lat = models.DecimalField(
        "Latitude da Loja",
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Preenchido automaticamente a partir do CEP",
    )
    store_lng = models.DecimalField(
        "Longitude da Loja",
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Preenchido automaticamente a partir do CEP",
    )
    motoboy_price_per_km = models.DecimalField(
        "Preço por Km (Motoboy)",
        max_digits=6,
        decimal_places=2,
        default=2.50,
        help_text="Valor cobrado por quilômetro",
    )
    motoboy_min_price = models.DecimalField(
        "Valor Mínimo Motoboy",
        max_digits=8,
        decimal_places=2,
        default=10.00,
        help_text="Valor mínimo cobrado",
    )
    motoboy_max_price = models.DecimalField(
        "Valor Máximo Motoboy",
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Deixe vazio para não ter limite",
    )
    motoboy_max_radius = models.DecimalField(
        "Raio Máximo (km)",
        max_digits=6,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Distância máxima atendida. Deixe vazio para sem limite.",
    )

    # ==================== WHATSAPP / EVOLUTION API ====================
    # URL e API Key Global são do settings.py (apenas para criar instância)
    # Cada tenant tem seu próprio token de instância (gerado ao criar)
    whatsapp_enabled = models.BooleanField("WhatsApp Ativo", default=False)
    evolution_instance = models.CharField(
        "Nome da Instância",
        max_length=100,
        blank=True,
        unique=True,
        null=True,
        help_text="Nome único da instância (será criada automaticamente)",
    )
    evolution_instance_token = models.CharField(
        "Token da Instância",
        max_length=200,
        blank=True,
        help_text="Token individual da instância (gerado automaticamente)",
    )
    whatsapp_number = models.CharField(
        "Número do WhatsApp",
        max_length=20,
        blank=True,
        help_text="Número conectado (preenchido automaticamente)",
    )
    whatsapp_connected = models.BooleanField(
        "WhatsApp Conectado",
        default=False,
        editable=False,
    )

    # ==================== CONTROLE GRANULAR DE NOTIFICAÇÕES ====================
    # Cada tipo de mensagem pode ser ativado/desativado individualmente
    notify_order_created = models.BooleanField("Notificar: Pedido Criado", default=True)
    notify_order_confirmed = models.BooleanField("Notificar: Pedido Confirmado", default=False)
    notify_payment_link = models.BooleanField("Notificar: Link de Pagamento", default=True)
    notify_payment_received = models.BooleanField("Notificar: Pagamento Recebido", default=True)
    notify_payment_failed = models.BooleanField("Notificar: Pagamento Falhou", default=True)
    notify_payment_refunded = models.BooleanField("Notificar: Pagamento Estornado", default=True)
    notify_order_shipped = models.BooleanField("Notificar: Pedido Enviado", default=True)
    notify_order_delivered = models.BooleanField("Notificar: Pedido Entregue", default=True)
    notify_delivery_failed = models.BooleanField("Notificar: Tentativa de Entrega Falha", default=True)
    notify_order_ready_for_pickup = models.BooleanField("Notificar: Pronto para Retirada", default=True)
    notify_order_picked_up = models.BooleanField("Notificar: Pedido Retirado", default=False)
    notify_order_expired = models.BooleanField("Notificar: Pedido Expirado", default=True)
    notify_order_cancelled = models.BooleanField("Notificar: Pedido Cancelado", default=True)
    notify_order_returned = models.BooleanField("Notificar: Pedido Devolvido", default=True)

    # ==================== MENSAGENS - PEDIDO ====================
    msg_order_created = models.TextField(
        "Mensagem: Pedido Criado",
        blank=True,
        help_text="Placeholders: {nome}, {codigo}, {valor}, {loja}, {link_rastreio}",
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
        blank=True,
        help_text="Placeholders: {nome}, {codigo}, {loja}",
        default=(
            "Olá {nome}! ✅\n\n"
            "Seu pedido *{codigo}* foi confirmado e está sendo preparado!\n\n"
            "_{loja}_"
        ),
    )

    # ==================== MENSAGENS - PAGAMENTO ====================
    msg_payment_link = models.TextField(
        "Mensagem: Link de Pagamento",
        blank=True,
        help_text="Placeholders: {nome}, {codigo}, {valor}, {link_pagamento}, {loja}",
        default=(
            "Olá {nome}! 💳\n\n"
            "Segue o link de pagamento do pedido *{codigo}*:\n\n"
            "💰 Valor: R$ {valor}\n"
            "🔗 {link_pagamento}\n\n"
            "O link expira em 12 horas.\n\n"
            "_{loja}_"
        ),
    )

    msg_payment_received = models.TextField(
        "Mensagem: Pagamento Recebido",
        blank=True,
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
        blank=True,
        help_text="Placeholders: {nome}, {codigo}, {valor}, {loja}",
        default=(
            "Olá {nome}!\n\n"
            "O valor de R$ {valor} referente ao pedido *{codigo}* foi estornado.\n\n"
            "Em caso de dúvidas, entre em contato.\n"
            "_{loja}_"
        ),
    )

    msg_payment_failed = models.TextField(
        "Mensagem: Pagamento Falhou",
        blank=True,
        help_text="Placeholders: {nome}, {codigo}, {valor}, {loja}",
        default=(
            "Olá {nome}! ⚠️\n\n"
            "O pagamento do pedido *{codigo}* não foi aprovado.\n\n"
            "Por favor, tente novamente ou entre em contato.\n\n"
            "_{loja}_"
        ),
    )

    # ==================== MENSAGENS - ENTREGA ====================
    msg_order_shipped = models.TextField(
        "Mensagem: Pedido Enviado",
        blank=True,
        help_text="Placeholders: {nome}, {codigo}, {rastreio}, {rastreio_info}, {link_rastreio}, {loja}",
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
        blank=True,
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
        blank=True,
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
        blank=True,
        help_text="Placeholders: {nome}, {codigo}, {valor}, {endereco}, {pickup_code}, {loja}",
        default=(
            "Olá {nome}! 🏬\n\n"
            "Seu pedido *{codigo}* está pronto para retirada!\n"
            "Valor: R$ {valor}\n\n"
            "🔑 *Código de retirada: {pickup_code}*\n\n"
            "📍 Retire em:\n{endereco}\n\n"
            "⏰ Prazo: 48 horas\n\n"
            "Apresente o código na loja.\n"
            "_{loja}_"
        ),
    )

    msg_order_picked_up = models.TextField(
        "Mensagem: Pedido Retirado",
        blank=True,
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
        blank=True,
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
        blank=True,
        help_text="Placeholders: {nome}, {codigo}, {motivo}, {motivo_info}, {loja}",
        default=(
            "Olá {nome}!\n\n"
            "Seu pedido *{codigo}* foi cancelado.\n"
            "{motivo_info}"
            "Em caso de dúvidas, entre em contato.\n"
            "_{loja}_"
        ),
    )

    msg_order_returned = models.TextField(
        "Mensagem: Pedido Devolvido",
        blank=True,
        help_text="Placeholders: {nome}, {codigo}, {motivo}, {motivo_info}, {loja}",
        default=(
            "Olá {nome}!\n\n"
            "Registramos a devolução do pedido *{codigo}*.\n"
            "{motivo_info}"
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
        from django.conf import settings
        # Precisa ter: URL global + instância + token da instância
        return bool(
            getattr(settings, 'EVOLUTION_API_URL', '')
            and self.evolution_instance
            and self.evolution_instance_token
        )

    @property
    def is_whatsapp_ready(self):
        """Verifica se WhatsApp está pronto para enviar (configurado + habilitado + conectado)."""
        return (
            self.is_whatsapp_configured
            and self.whatsapp_enabled
            and self.whatsapp_connected
        )

    def can_send_notification(self, notification_type: str) -> bool:
        """
        Verifica se pode enviar um tipo específico de notificação.

        Args:
            notification_type: Tipo da notificação (ex: 'order_created', 'payment_received')

        Returns:
            bool: True se pode enviar
        """
        if not self.whatsapp_enabled:
            return False

        # Mapeia tipo para campo
        field_map = {
            'order_created': 'notify_order_created',
            'order_confirmed': 'notify_order_confirmed',
            'payment_link': 'notify_payment_link',
            'payment_received': 'notify_payment_received',
            'payment_failed': 'notify_payment_failed',
            'payment_refunded': 'notify_payment_refunded',
            'order_shipped': 'notify_order_shipped',
            'order_delivered': 'notify_order_delivered',
            'delivery_failed': 'notify_delivery_failed',
            'ready_for_pickup': 'notify_order_ready_for_pickup',
            'picked_up': 'notify_order_picked_up',
            'expired': 'notify_order_expired',
            'cancelled': 'notify_order_cancelled',
            'returned': 'notify_order_returned',
        }

        field_name = field_map.get(notification_type)
        if not field_name:
            return True  # Tipo desconhecido, permite por padrão

        return getattr(self, field_name, True)


@receiver(post_save, sender=Tenant)
def create_tenant_settings(sender, instance, created, **kwargs):
    """Garante que todo tenant tenha configurações."""
    if created:
        TenantSettings.objects.create(tenant=instance)
