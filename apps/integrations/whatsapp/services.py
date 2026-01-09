"""
WhatsApp Notification Service - Flowlog.
Usa Evolution API + NotificationLog para confiabilidade.
"""

import logging
import uuid
from django.utils import timezone
from apps.integrations.whatsapp.client import EvolutionClient
from apps.integrations.models import NotificationLog

logger = logging.getLogger(__name__)


class WhatsAppNotificationService:

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
        if not self.settings or not self.settings.whatsapp_enabled or not self.client:
            return False
        if notification_type and not self.settings.can_send_notification(notification_type):
            return False
        return True

    def _get_tracking_link(self, order):
        from django.conf import settings as django_settings
        base_url = getattr(django_settings, 'SITE_URL', 'https://flowlog.app')
        return f"{base_url}/rastreio/{order.code}"

    def _format_value(self, value):
        return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def _get_first_name(self, full_name):
        return full_name.split()[0] if full_name else "Cliente"

    def _format_message(self, template, order, **extra):
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
        except KeyError:
            return template

    def _send(self, phone, message, notification_type, order=None):
        """Envia mensagem com logging completo."""
        correlation_id = str(uuid.uuid4())[:12]
        
        # Cria log inicial
        log = NotificationLog.objects.create(
            correlation_id=correlation_id,
            tenant=self.tenant,
            order=order,
            notification_type=notification_type,
            status=NotificationLog.Status.PENDING,
            recipient_phone=phone[-4:] if phone else "????",
            recipient_name=order.customer.name if order else "",
            message_preview=message[:200] if message else "",
        )
        
        if not self._can_send(notification_type):
            log.mark_blocked("Notificação desabilitada ou WhatsApp não configurado")
            return {"success": False, "blocked": True, "log_id": str(log.id)}
        
        try:
            result = self.client.send_text_message(phone=phone, message=message)
            log.mark_sent(api_response=result if isinstance(result, dict) else {"status": "sent"})
            return {"success": True, "log_id": str(log.id)}
        except Exception as e:
            logger.error("WhatsApp error [%s]: %s", correlation_id, str(e))
            log.mark_failed(error_message=str(e))
            return {"success": False, "error": str(e), "log_id": str(log.id)}

    # === PEDIDO ===

    def send_order_created(self, order):
        template = getattr(self.settings, 'msg_order_created', None) or (
            "Olá {nome}! 🎉\n\nSeu pedido *{codigo}* foi recebido!\nValor: R$ {valor}\n\nAcompanhe em: {link_rastreio}\n\n_{loja}_"
        )
        return self._send(order.customer.phone_normalized, self._format_message(template, order), 'order_created', order)

    def send_order_confirmed(self, order):
        template = getattr(self.settings, 'msg_order_confirmed', None) or (
            "Olá {nome}! ✅\n\nSeu pedido *{codigo}* foi confirmado!\n\n_{loja}_"
        )
        return self._send(order.customer.phone_normalized, self._format_message(template, order), 'order_confirmed', order)

    # === PAGAMENTO ===

    def send_payment_received(self, order):
        template = getattr(self.settings, 'msg_payment_received', None) or (
            "Olá {nome}! 💰\n\nPagamento do pedido *{codigo}* confirmado!\nValor: R$ {valor}\n\n_{loja}_"
        )
        return self._send(order.customer.phone_normalized, self._format_message(template, order), 'payment_received', order)

    def send_payment_refunded(self, order):
        template = getattr(self.settings, 'msg_payment_refunded', None) or (
            "Olá {nome}!\n\nO valor de R$ {valor} do pedido *{codigo}* foi estornado.\n\n_{loja}_"
        )
        return self._send(order.customer.phone_normalized, self._format_message(template, order), 'payment_refunded', order)

    # === ENTREGA ===

    def send_order_shipped(self, order):
        rastreio = f"Código de rastreio: *{order.tracking_code}*\n\n" if order.tracking_code else ""
        template = getattr(self.settings, 'msg_order_shipped', None) or (
            "Olá {nome}! 📦\n\nSeu pedido *{codigo}* foi enviado!\n\n{rastreio_info}Acompanhe em: {link_rastreio}\n\n_{loja}_"
        )
        return self._send(order.customer.phone_normalized, self._format_message(template, order, rastreio_info=rastreio), 'order_shipped', order)

    def send_order_delivered(self, order):
        template = getattr(self.settings, 'msg_order_delivered', None) or (
            "Olá {nome}! ✅\n\nSeu pedido *{codigo}* foi entregue!\n\nObrigado! 😊\n_{loja}_"
        )
        return self._send(order.customer.phone_normalized, self._format_message(template, order), 'order_delivered', order)

    def send_delivery_failed(self, order):
        template = getattr(self.settings, 'msg_delivery_failed', None) or (
            "Olá {nome}! ⚠️\n\nTentamos entregar o pedido *{codigo}* mas não conseguimos.\nTentativa: {tentativa}\n\n_{loja}_"
        )
        return self._send(order.customer.phone_normalized, self._format_message(template, order, tentativa=str(order.delivery_attempts)), 'delivery_failed', order)

    # === RETIRADA ===

    def send_order_ready_for_pickup(self, order):
        template = getattr(self.settings, 'msg_order_ready_for_pickup', None) or (
            "Olá {nome}! 🏬\n\nSeu pedido *{codigo}* está pronto!\nValor: R$ {valor}\n\n🔑 *Código: {pickup_code}*\n\n📍 {endereco}\n⏰ Prazo: 48h\n\n_{loja}_"
        )
        return self._send(order.customer.phone_normalized, self._format_message(template, order, pickup_code=order.pickup_code or "----"), 'ready_for_pickup', order)

    def send_order_picked_up(self, order):
        template = getattr(self.settings, 'msg_order_picked_up', None) or (
            "Olá {nome}! ✅\n\nPedido *{codigo}* retirado!\n\nObrigado! 😊\n_{loja}_"
        )
        return self._send(order.customer.phone_normalized, self._format_message(template, order), 'picked_up', order)

    def send_order_expired(self, order):
        template = getattr(self.settings, 'msg_order_expired', None) or (
            "Olá {nome}! ⚠️\n\nO prazo para retirada do pedido *{codigo}* expirou.\n\nEntre em contato.\n_{loja}_"
        )
        return self._send(order.customer.phone_normalized, self._format_message(template, order), 'expired', order)

    # === CANCELAMENTO ===

    def send_order_cancelled(self, order):
        motivo = f"Motivo: {order.cancel_reason}\n\n" if order.cancel_reason else ""
        template = getattr(self.settings, 'msg_order_cancelled', None) or (
            "Olá {nome}!\n\nSeu pedido *{codigo}* foi cancelado.\n{motivo_info}Em caso de dúvidas, entre em contato.\n_{loja}_"
        )
        return self._send(order.customer.phone_normalized, self._format_message(template, order, motivo_info=motivo), 'cancelled', order)

    def send_order_returned(self, order):
        motivo = f"Motivo: {order.return_reason}\n\n" if order.return_reason else ""
        template = getattr(self.settings, 'msg_order_returned', None) or (
            "Olá {nome}!\n\nDevolução do pedido *{codigo}* registrada.\n{motivo_info}_{loja}_"
        )
        return self._send(order.customer.phone_normalized, self._format_message(template, order, motivo_info=motivo), 'returned', order)
