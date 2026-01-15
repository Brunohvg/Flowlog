"""
WhatsApp Notification Service - Flowlog.
Usa Evolution API + NotificationLog para confiabilidade.
Suporta tanto Order (objeto) quanto Snapshot (dict) para evitar race condition.
"""

import logging
import uuid
from decimal import Decimal

from django.core.cache import cache
from apps.integrations.models import NotificationLog
from apps.integrations.whatsapp.client import EvolutionClient

logger = logging.getLogger(__name__)


class WhatsAppNotificationService:

    def __init__(self, tenant):
        self.tenant = tenant
        self.settings = getattr(tenant, "settings", None)
        self.client = None

        if (
            self.settings
            and self.settings.evolution_instance
            and self.settings.evolution_instance_token
        ):
            from django.conf import settings as django_settings

            api_url = getattr(django_settings, "EVOLUTION_API_URL", "")
            if api_url:
                self.client = EvolutionClient(
                    base_url=api_url,
                    api_key=self.settings.evolution_instance_token,
                    instance=self.settings.evolution_instance,
                )

    def _can_send(self, notification_type: str = None):
        if not self.settings or not self.settings.whatsapp_enabled or not self.client:
            return False
        if notification_type and not self.settings.can_send_notification(
            notification_type
        ):
            return False
        return True

    def _get_tracking_link(self, code: str):
        from django.conf import settings as django_settings

        base_url = getattr(django_settings, "SITE_URL", "https://flowlog.app")
        return f"{base_url}/rastreio/{code}"

    def _format_value(self, value):
        """Formata valor para BRL de forma robusta."""
        if value is None:
            return "0,00"

        try:
            # Se vier do JSON como float ou int
            if isinstance(value, (float, int)):
                value = Decimal(str(value))
            elif isinstance(value, str):
                # Se vier "12.50" (US) ou "12,50" (BR)
                value = value.replace(",", ".")
                value = Decimal(value)

            return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        except Exception:
            # Fallback seguro para não travar a mensagem
            return str(value)

    def _get_first_name(self, full_name):
        return full_name.split()[0] if full_name else "Cliente"

    def _extract_data(self, order_or_snapshot):
        """
        Extrai dados de um Order (objeto) ou Snapshot (dict).
        """
        if isinstance(order_or_snapshot, dict):
            # É um snapshot
            return {
                "code": order_or_snapshot.get("code", ""),
                "total_value": order_or_snapshot.get("total_value", "0"),
                "customer_name": order_or_snapshot.get("customer_name", "Cliente"),
                "customer_phone": order_or_snapshot.get("customer_phone", ""),
                "tracking_code": order_or_snapshot.get("tracking_code", ""),
                "pickup_code": order_or_snapshot.get("pickup_code", ""),
                "delivery_attempts": order_or_snapshot.get("delivery_attempts", 0),
                "cancel_reason": order_or_snapshot.get("cancel_reason", ""),
                "return_reason": order_or_snapshot.get("return_reason", ""),
                "order_obj": None,
            }
        else:
            # É um objeto Order
            return {
                "code": order_or_snapshot.code,
                "total_value": order_or_snapshot.total_value,
                "customer_name": (
                    order_or_snapshot.customer.name
                    if order_or_snapshot.customer
                    else "Cliente"
                ),
                "customer_phone": (
                    order_or_snapshot.customer.phone_normalized
                    if order_or_snapshot.customer
                    else ""
                ),
                "tracking_code": order_or_snapshot.tracking_code or "",
                "pickup_code": order_or_snapshot.pickup_code or "",
                "delivery_attempts": order_or_snapshot.delivery_attempts,
                "cancel_reason": order_or_snapshot.cancel_reason or "",
                "return_reason": order_or_snapshot.return_reason or "",
                "order_obj": order_or_snapshot,
            }

    def _format_message_from_data(self, template, data, **extra):
        """Formata mensagem usando dados extraídos."""
        placeholders = {
            "nome": self._get_first_name(data["customer_name"]),
            "codigo": data["code"],
            "valor": self._format_value(data["total_value"]),
            "loja": self.tenant.name,
            "link_rastreio": self._get_tracking_link(data["code"]),
            "endereco": getattr(self.tenant, "address", "") or "Consulte a loja",
            **extra,
        }
        try:
            return template.format(**placeholders)
        except KeyError:
            return template

    def _send(self, phone, message, notification_type, order=None):
        """
        Envia mensagem com logging completo.
        """
        correlation_id = str(uuid.uuid4())[:12]

        if not phone:
            logger.warning("[WhatsApp] Telefone vazio, ignorando envio")
            return {"success": False, "error": "phone_empty"}

        # Trava de Idempotência (Mitiga disparos duplicados em 10 min)
        # Chave: notif:idemp:{tenant}:{order_id}:{type}
        idemp_key = f"notif:idemp:{self.tenant.id}:{order.id if order else 'standalone'}:{notification_type}"
        if not cache.add(idemp_key, "locked", timeout=600):
            logger.warning("[WhatsApp] Idempotência: Notificação duplicada bloqueada para %s", idemp_key)
            return {"success": False, "error": "duplicate_idempotency"}

        log = None
        try:
            log = NotificationLog.objects.create(
                correlation_id=correlation_id,
                tenant=self.tenant,
                order=order,
                notification_type=notification_type,
                status=NotificationLog.Status.PENDING,
                recipient_phone=phone[-4:] if phone else "????",
                recipient_name=(
                    order.customer.name
                    if order and hasattr(order, "customer") and order.customer
                    else ""
                ),
                message_preview=message[:200] if message else "",
                error_message="",
            )
        except Exception as e:
            logger.warning("[WhatsApp] Falha ao criar log: %s", e)

        # Verifica se pode enviar
        if not self._can_send(notification_type):
            if log:
                log.mark_blocked("Notificação desabilitada ou WhatsApp não configurado")
            return {
                "success": False,
                "blocked": True,
                "log_id": str(log.id) if log else None,
            }

        # Envia mensagem
        try:
            result = self.client.send_text_message(
                phone=phone, message=message, correlation_id=correlation_id
            )
            if log:
                log.mark_sent(
                    api_response=(
                        result if isinstance(result, dict) else {"status": "sent"}
                    )
                )
            return {"success": True, "log_id": str(log.id) if log else None}
        except Exception as e:
            logger.error("[WhatsApp] Erro envio [%s]: %s", correlation_id, str(e))
            if log:
                log.mark_failed(error_message=str(e))
            return {
                "success": False,
                "error": str(e),
                "log_id": str(log.id) if log else None,
            }

    # === PEDIDO ===

    def send_order_created(self, order_or_snapshot):
        data = self._extract_data(order_or_snapshot)
        template = getattr(self.settings, "msg_order_created", None) or (
            "Olá {nome}! 🎉\n\nSeu pedido *{codigo}* foi recebido!\nValor: R$ {valor}\n\nAcompanhe em: {link_rastreio}\n\n_{loja}_"
        )
        return self._send(
            data["customer_phone"],
            self._format_message_from_data(template, data),
            "order_created",
            data["order_obj"],
        )

    def send_order_confirmed(self, order_or_snapshot):
        data = self._extract_data(order_or_snapshot)
        template = getattr(self.settings, "msg_order_confirmed", None) or (
            "Olá {nome}! ✅\n\nSeu pedido *{codigo}* foi confirmado!\n\n_{loja}_"
        )
        return self._send(
            data["customer_phone"],
            self._format_message_from_data(template, data),
            "order_confirmed",
            data["order_obj"],
        )

    # === PAGAMENTO ===

    def send_payment_received(self, order_or_snapshot):
        data = self._extract_data(order_or_snapshot)
        template = getattr(self.settings, "msg_payment_received", None) or (
            "Olá {nome}! 💰\n\nPagamento do pedido *{codigo}* confirmado!\nValor: R$ {valor}\n\n_{loja}_"
        )
        return self._send(
            data["customer_phone"],
            self._format_message_from_data(template, data),
            "payment_received",
            data["order_obj"],
        )

    def send_payment_link(self, order, payment_link):
        """Envia link de pagamento para o cliente."""
        data = self._extract_data(order)
        template = getattr(self.settings, "msg_payment_link", None) or (
            "Olá {nome}! 💳\n\n"
            "Segue o link de pagamento do pedido *{codigo}*:\n\n"
            "💰 Valor: R$ {valor}\n"
            "🔗 {link_pagamento}\n\n"
            "O link expira em 12 horas.\n\n"
            "_{loja}_"
        )
        return self._send(
            data["customer_phone"],
            self._format_message_from_data(
                template, data, link_pagamento=payment_link.checkout_url
            ),
            "payment_link",
            data["order_obj"],
        )

    def send_payment_refunded(self, order_or_snapshot):
        data = self._extract_data(order_or_snapshot)
        template = getattr(self.settings, "msg_payment_refunded", None) or (
            "Olá {nome}!\n\nO valor de R$ {valor} do pedido *{codigo}* foi estornado.\n\n_{loja}_"
        )
        return self._send(
            data["customer_phone"],
            self._format_message_from_data(template, data),
            "payment_refunded",
            data["order_obj"],
        )

    def send_payment_failed(self, order_or_snapshot):
        """Notifica cliente que o pagamento falhou."""
        data = self._extract_data(order_or_snapshot)
        template = getattr(self.settings, "msg_payment_failed", None) or (
            "Olá {nome}! ⚠️\n\n"
            "O pagamento do pedido *{codigo}* não foi aprovado.\n\n"
            "Por favor, tente novamente ou entre em contato.\n\n"
            "_{loja}_"
        )
        return self._send(
            data["customer_phone"],
            self._format_message_from_data(template, data),
            "payment_failed",
            data["order_obj"],
        )

    # === ENTREGA ===

    def send_order_shipped(self, order_or_snapshot):
        data = self._extract_data(order_or_snapshot)
        rastreio = (
            f"Código de rastreio: *{data['tracking_code']}*\n\n"
            if data["tracking_code"]
            else ""
        )
        template = getattr(self.settings, "msg_order_shipped", None) or (
            "Olá {nome}! 📦\n\nSeu pedido *{codigo}* foi enviado!\n\n{rastreio_info}Acompanhe em: {link_rastreio}\n\n_{loja}_"
        )
        return self._send(
            data["customer_phone"],
            self._format_message_from_data(template, data, rastreio_info=rastreio),
            "order_shipped",
            data["order_obj"],
        )

    def send_order_delivered(self, order_or_snapshot):
        data = self._extract_data(order_or_snapshot)
        template = getattr(self.settings, "msg_order_delivered", None) or (
            "Olá {nome}! ✅\n\nSeu pedido *{codigo}* foi entregue!\n\nObrigado! 😊\n_{loja}_"
        )
        return self._send(
            data["customer_phone"],
            self._format_message_from_data(template, data),
            "order_delivered",
            data["order_obj"],
        )

    def send_delivery_failed(self, order_or_snapshot):
        data = self._extract_data(order_or_snapshot)
        template = getattr(self.settings, "msg_delivery_failed", None) or (
            "Olá {nome}! ⚠️\n\nTentamos entregar o pedido *{codigo}* mas não conseguimos.\nTentativa: {tentativa}\n\n_{loja}_"
        )
        return self._send(
            data["customer_phone"],
            self._format_message_from_data(
                template, data, tentativa=str(data["delivery_attempts"])
            ),
            "delivery_failed",
            data["order_obj"],
        )

    # === RETIRADA ===

    def send_order_ready_for_pickup(self, order_or_snapshot):
        data = self._extract_data(order_or_snapshot)
        template = getattr(self.settings, "msg_order_ready_for_pickup", None) or (
            "Olá {nome}! 🏬\n\nSeu pedido *{codigo}* está pronto!\nValor: R$ {valor}\n\n🔑 *Código: {pickup_code}*\n\n📍 {endereco}\n⏰ Prazo: 48h\n\n_{loja}_"
        )
        return self._send(
            data["customer_phone"],
            self._format_message_from_data(
                template, data, pickup_code=data["pickup_code"] or "----"
            ),
            "ready_for_pickup",
            data["order_obj"],
        )

    def send_order_picked_up(self, order_or_snapshot):
        data = self._extract_data(order_or_snapshot)
        template = getattr(self.settings, "msg_order_picked_up", None) or (
            "Olá {nome}! ✅\n\nPedido *{codigo}* retirado!\n\nObrigado! 😊\n_{loja}_"
        )
        return self._send(
            data["customer_phone"],
            self._format_message_from_data(template, data),
            "picked_up",
            data["order_obj"],
        )

    def send_order_expired(self, order_or_snapshot):
        data = self._extract_data(order_or_snapshot)
        template = getattr(self.settings, "msg_order_expired", None) or (
            "Olá {nome}! ⚠️\n\nO prazo para retirada do pedido *{codigo}* expirou.\n\nEntre em contato.\n_{loja}_"
        )
        return self._send(
            data["customer_phone"],
            self._format_message_from_data(template, data),
            "expired",
            data["order_obj"],
        )

    # === CANCELAMENTO ===

    def send_order_cancelled(self, order_or_snapshot):
        data = self._extract_data(order_or_snapshot)
        motivo = f"Motivo: {data['cancel_reason']}\n\n" if data["cancel_reason"] else ""
        template = getattr(self.settings, "msg_order_cancelled", None) or (
            "Olá {nome}!\n\nSeu pedido *{codigo}* foi cancelado.\n{motivo_info}Em caso de dúvidas, entre em contato.\n_{loja}_"
        )
        return self._send(
            data["customer_phone"],
            self._format_message_from_data(template, data, motivo_info=motivo),
            "cancelled",
            data["order_obj"],
        )

    def send_order_returned(self, order_or_snapshot):
        data = self._extract_data(order_or_snapshot)
        motivo = f"Motivo: {data['return_reason']}\n\n" if data["return_reason"] else ""
        template = getattr(self.settings, "msg_order_returned", None) or (
            "Olá {nome}!\n\nDevolução do pedido *{codigo}* registrada.\n{motivo_info}_{loja}_"
        )
        return self._send(
            data["customer_phone"],
            self._format_message_from_data(template, data, motivo_info=motivo),
            "returned",
            data["order_obj"],
        )
