"""
Serviço de notificações via WhatsApp.
"""

import logging

from django.conf import settings

from apps.integrations.whatsapp.client import EvolutionClient

logger = logging.getLogger(__name__)


class WhatsAppNotificationService:
    """
    Serviço para envio de notificações via WhatsApp.
    Usa a Evolution API para enviar mensagens.
    """

    def __init__(self, tenant):
        self.tenant = tenant
        self.tenant_settings = getattr(tenant, 'settings', None)

        self.client = EvolutionClient(
            base_url=settings.EVOLUTION_API_URL,
            api_key=settings.EVOLUTION_API_KEY,
            instance=settings.EVOLUTION_INSTANCE,
        )

    def _is_enabled(self) -> bool:
        """Verifica se WhatsApp está habilitado para o tenant."""
        if not settings.EVOLUTION_API_URL or not settings.EVOLUTION_API_KEY:
            return False
        if self.tenant_settings:
            return bool(self.tenant_settings.whatsapp_enabled)
        return True

    def _format_value(self, value) -> str:
        """Formata valor para exibição (R$ 1.234,56)."""
        return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def _get_first_name(self, full_name: str) -> str:
        """Retorna primeiro nome."""
        return full_name.split()[0] if full_name else "Cliente"

    def send_order_created(self, order):
        """Envia notificação de pedido criado."""
        if not self._is_enabled():
            logger.info(
                "WhatsApp disabled | tenant=%s | order=%s",
                self.tenant.id,
                order.id,
            )
            return

        logger.info(
            "Send WhatsApp | event=order_created | order=%s",
            order.code,
        )

        # Template do tenant ou padrão
        if self.tenant_settings and self.tenant_settings.msg_order_created:
            template = self.tenant_settings.msg_order_created
        else:
            template = (
                "Olá {nome}! 🎉\n\n"
                "Seu pedido *{codigo}* foi recebido!\n"
                "Valor: R$ {valor}\n\n"
                "Obrigado pela preferência!"
            )

        message = template.format(
            nome=self._get_first_name(order.customer.name),
            codigo=order.code,
            valor=self._format_value(order.total_value),
        )

        self.client.send_text_message(
            phone=order.customer.phone,
            message=message,
        )

    def send_order_shipped(self, order):
        """Envia notificação de pedido enviado."""
        if not self._is_enabled():
            return

        logger.info(
            "Send WhatsApp | event=order_shipped | order=%s | tracking=%s",
            order.code,
            order.tracking_code or "N/A",
        )

        # Template do tenant ou padrão
        if self.tenant_settings and self.tenant_settings.msg_order_shipped:
            template = self.tenant_settings.msg_order_shipped
        else:
            template = (
                "Olá {nome}! 📦\n\n"
                "Seu pedido *{codigo}* foi enviado!\n"
            )

        message = template.format(
            nome=self._get_first_name(order.customer.name),
            codigo=order.code,
        )

        # Adiciona código de rastreio se disponível
        if order.tracking_code:
            message += f"\n🔍 Código de rastreio: *{order.tracking_code}*\n"
            if order.tracking_url:
                message += f"\nAcompanhe em:\n{order.tracking_url}\n"

        message += "\nEm breve chegará no endereço informado!"

        self.client.send_text_message(
            phone=order.customer.phone,
            message=message,
        )

    def send_order_delivered(self, order):
        """Envia notificação de pedido entregue."""
        if not self._is_enabled():
            return

        logger.info(
            "Send WhatsApp | event=order_delivered | order=%s",
            order.code,
        )

        # Template do tenant ou padrão
        if self.tenant_settings and self.tenant_settings.msg_order_delivered:
            template = self.tenant_settings.msg_order_delivered
        else:
            template = (
                "Olá {nome}! ✅\n\n"
                "Seu pedido *{codigo}* foi entregue!\n\n"
                "Obrigado por comprar conosco!"
            )

        message = template.format(
            nome=self._get_first_name(order.customer.name),
            codigo=order.code,
        )

        self.client.send_text_message(
            phone=order.customer.phone,
            message=message,
        )

    def send_order_ready_for_pickup(self, order):
        """Envia notificação de pedido pronto para retirada."""
        if not self._is_enabled():
            return

        logger.info(
            "Send WhatsApp | event=ready_for_pickup | order=%s",
            order.code,
        )

        # Template padrão (pode ser customizado no tenant_settings no futuro)
        message = (
            f"Olá {self._get_first_name(order.customer.name)}! 🏬\n\n"
            f"Seu pedido *{order.code}* está pronto para retirada!\n\n"
            f"Valor: R$ {self._format_value(order.total_value)}\n\n"
            "Aguardamos você em nossa loja! 😊"
        )

        self.client.send_text_message(
            phone=order.customer.phone,
            message=message,
        )
