"""
Services de notificação via WhatsApp - Flowlog.
Usa Evolution API para envio de mensagens.
Cada tenant configura sua própria instância.

IMPORTANTE: Verifica controle granular antes de enviar cada tipo de mensagem.
"""

import logging

from apps.integrations.whatsapp.client import EvolutionClient

logger = logging.getLogger(__name__)


class WhatsAppNotificationService:
    """
    Service para envio de notificações via WhatsApp.
    
    Segurança:
    - URL global vem do settings.py
    - Token é individual por instância (salvo no tenant)
    - Cada tenant só pode enviar para sua própria instância
    
    Controle:
    - Verifica whatsapp_enabled antes de qualquer envio
    - Verifica notify_* específico para cada tipo de mensagem
    """

    def __init__(self, tenant):
        self.tenant = tenant
        self.settings = getattr(tenant, "settings", None)
        self.client = None

        if self.settings and self.settings.evolution_instance and self.settings.evolution_instance_token:
            from django.conf import settings as django_settings
            
            api_url = getattr(django_settings, 'EVOLUTION_API_URL', '')
            
            if api_url:
                self.client = EvolutionClient(
                    base_url=api_url,
                    api_key=self.settings.evolution_instance_token,
                    instance=self.settings.evolution_instance,
                )

    def _can_send(self, notification_type: str = None):
        """
        Verifica se pode enviar mensagens.
        
        Args:
            notification_type: Tipo específico da notificação para verificação granular
        """
        if not self.settings:
            logger.warning("Tenant %s sem configurações", self.tenant.id)
            return False
        
        if not self.settings.whatsapp_enabled:
            logger.debug("WhatsApp desabilitado para tenant %s", self.tenant.id)
            return False
        
        if not self.client:
            logger.warning("WhatsApp não configurado para tenant %s", self.tenant.id)
            return False
        
        # Verificação granular por tipo de notificação
        if notification_type and not self.settings.can_send_notification(notification_type):
            logger.debug(
                "Notificação '%s' desabilitada para tenant %s",
                notification_type, self.tenant.id
            )
            return False
        
        return True

    def _get_tracking_link(self, order):
        """Gera link de rastreamento."""
        from django.conf import settings as django_settings
        base_url = getattr(django_settings, 'SITE_URL', 'https://flowlog.app')
        return f"{base_url}/rastreio/{order.code}"

    def _format_value(self, value):
        """Formata valor para exibição (R$ 1.234,56)."""
        return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def _get_first_name(self, full_name):
        """Retorna primeiro nome."""
        return full_name.split()[0] if full_name else "Cliente"

    def _format_message(self, template, order, **extra):
        """Formata mensagem com placeholders."""
        placeholders = {
            "nome": self._get_first_name(order.customer.name),
            "codigo": order.code,
            "valor": self._format_value(order.total_value),
            "loja": self.tenant.name,
            "link_rastreio": self._get_tracking_link(order),
            "endereco": getattr(self.tenant, 'address', '') or "Consulte a loja",
            **extra,
        }
        
        try:
            return template.format(**placeholders)
        except KeyError as e:
            logger.error("Placeholder inválido na mensagem: %s", e)
            return template

    def _send(self, phone, message, notification_type: str = None):
        """Envia mensagem via Evolution API."""
        if not self._can_send(notification_type):
            return False

        try:
            self.client.send_text_message(phone=phone, message=message)
            logger.info(
                "WhatsApp enviado | tenant=%s | type=%s | phone=***%s",
                self.tenant.id, notification_type or "unknown", phone[-4:]
            )
            return True
        except Exception as e:
            logger.error("Erro ao enviar WhatsApp: %s", e)
            return False

    # ==================== PEDIDO ====================

    def send_order_created(self, order):
        """Notifica criação do pedido."""
        template = getattr(self.settings, 'msg_order_created', None) or (
            "Olá {nome}! 🎉\n\n"
            "Seu pedido *{codigo}* foi recebido!\n"
            "Valor: R$ {valor}\n\n"
            "Acompanhe em: {link_rastreio}\n\n"
            "_{loja}_"
        )
        message = self._format_message(template, order)
        return self._send(order.customer.phone_normalized, message, 'order_created')

    def send_order_confirmed(self, order):
        """Notifica confirmação do pedido."""
        template = getattr(self.settings, 'msg_order_confirmed', None) or (
            "Olá {nome}! ✅\n\n"
            "Seu pedido *{codigo}* foi confirmado!\n\n"
            "_{loja}_"
        )
        message = self._format_message(template, order)
        return self._send(order.customer.phone_normalized, message, 'order_confirmed')

    # ==================== PAGAMENTO ====================

    def send_payment_received(self, order):
        """Notifica pagamento recebido."""
        template = getattr(self.settings, 'msg_payment_received', None) or (
            "Olá {nome}! 💰\n\n"
            "Pagamento do pedido *{codigo}* confirmado!\n"
            "Valor: R$ {valor}\n\n"
            "_{loja}_"
        )
        message = self._format_message(template, order)
        return self._send(order.customer.phone_normalized, message, 'payment_received')

    def send_payment_refunded(self, order):
        """Notifica estorno de pagamento."""
        template = getattr(self.settings, 'msg_payment_refunded', None) or (
            "Olá {nome}!\n\n"
            "O valor de R$ {valor} do pedido *{codigo}* foi estornado.\n\n"
            "_{loja}_"
        )
        message = self._format_message(template, order)
        return self._send(order.customer.phone_normalized, message, 'payment_refunded')

    # ==================== ENTREGA ====================

    def send_order_shipped(self, order):
        """Notifica envio do pedido."""
        rastreio_info = ""
        if order.tracking_code:
            rastreio_info = f"Código de rastreio: *{order.tracking_code}*\n\n"
        
        template = getattr(self.settings, 'msg_order_shipped', None) or (
            "Olá {nome}! 📦\n\n"
            "Seu pedido *{codigo}* foi enviado!\n\n"
            "{rastreio_info}"
            "Acompanhe em: {link_rastreio}\n\n"
            "_{loja}_"
        )
        message = self._format_message(
            template, order,
            rastreio=order.tracking_code or "",
            rastreio_info=rastreio_info,
        )
        return self._send(order.customer.phone_normalized, message, 'order_shipped')

    def send_order_delivered(self, order):
        """Notifica entrega do pedido."""
        template = getattr(self.settings, 'msg_order_delivered', None) or (
            "Olá {nome}! ✅\n\n"
            "Seu pedido *{codigo}* foi entregue!\n\n"
            "Obrigado! 😊\n"
            "_{loja}_"
        )
        message = self._format_message(template, order)
        return self._send(order.customer.phone_normalized, message, 'order_delivered')

    def send_delivery_failed(self, order):
        """Notifica tentativa de entrega falha."""
        template = getattr(self.settings, 'msg_delivery_failed', None) or (
            "Olá {nome}! ⚠️\n\n"
            "Tentamos entregar o pedido *{codigo}* mas não conseguimos.\n"
            "Tentativa: {tentativa}\n\n"
            "Verifique o endereço ou entre em contato.\n"
            "_{loja}_"
        )
        message = self._format_message(
            template, order,
            tentativa=str(order.delivery_attempts),
        )
        return self._send(order.customer.phone_normalized, message, 'delivery_failed')

    # ==================== RETIRADA ====================

    def send_order_ready_for_pickup(self, order):
        """Notifica pedido pronto para retirada com código de 4 dígitos."""
        template = getattr(self.settings, 'msg_order_ready_for_pickup', None) or (
            "Olá {nome}! 🏬\n\n"
            "Seu pedido *{codigo}* está pronto para retirada!\n"
            "Valor: R$ {valor}\n\n"
            "🔑 *Código de retirada: {pickup_code}*\n\n"
            "📍 Retire em:\n{endereco}\n\n"
            "⏰ Prazo: 48 horas\n\n"
            "Apresente o código na loja.\n"
            "_{loja}_"
        )
        message = self._format_message(
            template, order,
            pickup_code=order.pickup_code or "----",
        )
        return self._send(order.customer.phone_normalized, message, 'ready_for_pickup')

    def send_order_picked_up(self, order):
        """Notifica retirada do pedido."""
        template = getattr(self.settings, 'msg_order_picked_up', None) or (
            "Olá {nome}! ✅\n\n"
            "Pedido *{codigo}* retirado!\n\n"
            "Obrigado! 😊\n"
            "_{loja}_"
        )
        message = self._format_message(template, order)
        return self._send(order.customer.phone_normalized, message, 'picked_up')

    def send_order_expired(self, order):
        """Notifica expiração do pedido (retirada não realizada)."""
        template = getattr(self.settings, 'msg_order_expired', None) or (
            "Olá {nome}! ⚠️\n\n"
            "O prazo para retirada do pedido *{codigo}* expirou.\n\n"
            "Entre em contato para verificar as opções.\n"
            "_{loja}_"
        )
        message = self._format_message(template, order)
        return self._send(order.customer.phone_normalized, message, 'expired')

    # ==================== CANCELAMENTO ====================

    def send_order_cancelled(self, order):
        """Notifica cancelamento do pedido."""
        motivo_info = ""
        if order.cancel_reason:
            motivo_info = f"Motivo: {order.cancel_reason}\n\n"
        
        template = getattr(self.settings, 'msg_order_cancelled', None) or (
            "Olá {nome}!\n\n"
            "Seu pedido *{codigo}* foi cancelado.\n"
            "{motivo_info}"
            "Em caso de dúvidas, entre em contato.\n"
            "_{loja}_"
        )
        message = self._format_message(
            template, order,
            motivo=order.cancel_reason or "",
            motivo_info=motivo_info,
        )
        return self._send(order.customer.phone_normalized, message, 'cancelled')

    def send_order_returned(self, order):
        """Notifica devolução do pedido."""
        motivo_info = ""
        if order.return_reason:
            motivo_info = f"Motivo: {order.return_reason}\n\n"
        
        template = getattr(self.settings, 'msg_order_returned', None) or (
            "Olá {nome}!\n\n"
            "Devolução do pedido *{codigo}* registrada.\n"
            "{motivo_info}\n"
            "_{loja}_"
        )
        message = self._format_message(
            template, order,
            motivo=order.return_reason or "",
            motivo_info=motivo_info,
        )
        return self._send(order.customer.phone_normalized, message, 'returned')
