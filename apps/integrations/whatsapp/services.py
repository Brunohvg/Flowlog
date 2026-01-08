"""
Services de notificação via WhatsApp - Flowlog.
Usa Evolution API para envio de mensagens.
Cada tenant configura sua própria instância.

IMPORTANTE: 
- Verifica controle granular antes de enviar cada tipo de mensagem
- Suporte a correlation_id para rastreamento de ponta a ponta
- Logging estruturado para diagnóstico de falhas
"""

import logging
import uuid
from typing import Optional, Tuple

from apps.integrations.whatsapp.client import EvolutionClient, EvolutionAPIError

logger = logging.getLogger("flowlog.whatsapp.notifications")


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
    
    Rastreamento:
    - correlation_id: ID único para rastrear toda a cadeia
    - celery_task_id: ID da task Celery que originou o envio
    """

    def __init__(
        self, 
        tenant, 
        *, 
        correlation_id: str = None, 
        celery_task_id: str = None
    ):
        """
        Inicializa o service.
        
        Args:
            tenant: Tenant para envio
            correlation_id: ID de correlação para rastreamento
            celery_task_id: ID da task Celery que originou
        """
        self.tenant = tenant
        self.settings = getattr(tenant, "settings", None)
        self.client = None
        self.correlation_id = correlation_id or str(uuid.uuid4())[:8]
        self.celery_task_id = celery_task_id

        if self.settings and self.settings.evolution_instance and self.settings.evolution_instance_token:
            from django.conf import settings as django_settings
            
            api_url = getattr(django_settings, 'EVOLUTION_API_URL', '')
            
            if api_url:
                self.client = EvolutionClient(
                    base_url=api_url,
                    api_key=self.settings.evolution_instance_token,
                    instance=self.settings.evolution_instance,
                    correlation_id=self.correlation_id,
                )
                
        logger.debug(
            "SERVICE_INIT | correlation_id=%s | tenant=%s | "
            "client_ready=%s | celery_task_id=%s",
            self.correlation_id, tenant.id, 
            self.client is not None, celery_task_id
        )

    def _can_send(self, notification_type: str = None) -> Tuple[bool, str]:
        """
        Verifica se pode enviar mensagens.
        
        Args:
            notification_type: Tipo específico da notificação para verificação granular
            
        Returns:
            Tuple[bool, str]: (pode_enviar, motivo_do_bloqueio)
        """
        if not self.settings:
            reason = "tenant_sem_configuracoes"
            logger.warning(
                "NOTIFICATION_BLOCKED | correlation_id=%s | tenant=%s | reason=%s",
                self.correlation_id, self.tenant.id, reason
            )
            return False, reason
        
        if not self.settings.whatsapp_enabled:
            reason = "whatsapp_desabilitado"
            logger.info(
                "NOTIFICATION_BLOCKED | correlation_id=%s | tenant=%s | reason=%s",
                self.correlation_id, self.tenant.id, reason
            )
            return False, reason
        
        if not self.client:
            reason = "cliente_nao_configurado"
            logger.warning(
                "NOTIFICATION_BLOCKED | correlation_id=%s | tenant=%s | reason=%s",
                self.correlation_id, self.tenant.id, reason
            )
            return False, reason
        
        # Verificação granular por tipo de notificação
        if notification_type and not self.settings.can_send_notification(notification_type):
            reason = f"notificacao_{notification_type}_desabilitada"
            logger.info(
                "NOTIFICATION_BLOCKED | correlation_id=%s | tenant=%s | "
                "reason=%s | type=%s",
                self.correlation_id, self.tenant.id, reason, notification_type
            )
            return False, reason
        
        return True, ""

    def _get_tracking_link(self, order) -> str:
        """Gera link de rastreamento."""
        from django.conf import settings as django_settings
        base_url = getattr(django_settings, 'SITE_URL', 'https://flowlog.app')
        return f"{base_url}/rastreio/{order.code}"

    def _format_value(self, value) -> str:
        """Formata valor para exibição (R$ 1.234,56)."""
        return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def _get_first_name(self, full_name: str) -> str:
        """Retorna primeiro nome."""
        return full_name.split()[0] if full_name else "Cliente"

    def _format_message(self, template: str, order, **extra) -> str:
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
            logger.error(
                "MESSAGE_FORMAT_ERROR | correlation_id=%s | "
                "error=placeholder_invalido | placeholder=%s",
                self.correlation_id, str(e)
            )
            return template

    def _create_notification_log(
        self, 
        order, 
        notification_type: str, 
        phone: str, 
        message: str
    ):
        """
        Cria log de notificação no banco (se modelo existir).
        
        Returns:
            NotificationLog ou None
        """
        try:
            from django.apps import apps
            NotificationLog = apps.get_model("integrations", "NotificationLog")
            
            log = NotificationLog.objects.create(
                tenant=self.tenant,
                order=order,
                notification_type=notification_type,
                recipient_phone=phone[-4:],  # Apenas últimos 4 dígitos
                recipient_name=order.customer.name,
                message_preview=message[:200],
                celery_task_id=self.celery_task_id,
                correlation_id=self.correlation_id,
            )
            
            logger.debug(
                "NOTIFICATION_LOG_CREATED | correlation_id=%s | log_id=%s",
                self.correlation_id, log.id
            )
            
            return log
            
        except LookupError:
            # Model não existe ainda
            return None
        except Exception as e:
            logger.warning(
                "NOTIFICATION_LOG_ERROR | correlation_id=%s | error=%s",
                self.correlation_id, str(e)
            )
            return None

    def _send(
        self, 
        phone: str, 
        message: str, 
        notification_type: str,
        order=None
    ) -> dict:
        """
        Envia mensagem via Evolution API.
        
        Args:
            phone: Telefone do destinatário
            message: Mensagem a enviar
            notification_type: Tipo da notificação
            order: Pedido relacionado (para logging)
            
        Returns:
            dict: {
                "success": bool,
                "blocked": bool (se foi bloqueado por configuração),
                "block_reason": str (motivo do bloqueio),
                "error": str (mensagem de erro),
                "api_response": dict (resposta da API),
                "notification_log_id": uuid (ID do log)
            }
        """
        result = {
            "success": False,
            "blocked": False,
            "block_reason": "",
            "error": "",
            "api_response": None,
            "notification_log_id": None,
        }
        
        # Verifica se pode enviar
        can_send, block_reason = self._can_send(notification_type)
        if not can_send:
            result["blocked"] = True
            result["block_reason"] = block_reason
            return result
        
        # Cria log de notificação
        notification_log = None
        if order:
            notification_log = self._create_notification_log(
                order, notification_type, phone, message
            )
            if notification_log:
                result["notification_log_id"] = str(notification_log.id)
        
        # Mascara telefone para log
        phone_masked = f"***{phone[-4:]}" if len(phone) >= 4 else "***"
        
        try:
            logger.info(
                "NOTIFICATION_SENDING | correlation_id=%s | type=%s | "
                "phone=%s | order=%s",
                self.correlation_id, notification_type, phone_masked,
                order.code if order else "N/A"
            )
            
            api_response = self.client.send_text_message(phone=phone, message=message)
            
            result["success"] = True
            result["api_response"] = api_response
            
            # Atualiza log como enviado
            if notification_log:
                notification_log.mark_sent(api_response)
            
            logger.info(
                "NOTIFICATION_SENT | correlation_id=%s | type=%s | "
                "phone=%s | order=%s",
                self.correlation_id, notification_type, phone_masked,
                order.code if order else "N/A"
            )
            
        except EvolutionAPIError as e:
            result["error"] = str(e)
            result["api_response"] = getattr(e, 'response', None)
            
            # Atualiza log como falha
            if notification_log:
                notification_log.mark_failed(
                    error_message=str(e),
                    error_code=getattr(e, 'status_code', None),
                    api_response=getattr(e, 'response', None)
                )
            
            logger.error(
                "NOTIFICATION_FAILED | correlation_id=%s | type=%s | "
                "phone=%s | order=%s | error_type=EvolutionAPIError | error=%s",
                self.correlation_id, notification_type, phone_masked,
                order.code if order else "N/A", str(e)
            )
            
        except Exception as e:
            result["error"] = str(e)
            
            # Atualiza log como falha
            if notification_log:
                notification_log.mark_failed(
                    error_message=str(e),
                    error_code="EXCEPTION"
                )
            
            logger.exception(
                "NOTIFICATION_EXCEPTION | correlation_id=%s | type=%s | "
                "phone=%s | order=%s | error_type=%s | error=%s",
                self.correlation_id, notification_type, phone_masked,
                order.code if order else "N/A", type(e).__name__, str(e)
            )
        
        return result

    # ==================== PEDIDO ====================

    def send_order_created(self, order) -> dict:
        """Notifica criação do pedido."""
        template = getattr(self.settings, 'msg_order_created', None) or (
            "Olá {nome}! 🎉\n\n"
            "Seu pedido *{codigo}* foi recebido!\n"
            "Valor: R$ {valor}\n\n"
            "Acompanhe em: {link_rastreio}\n\n"
            "_{loja}_"
        )
        message = self._format_message(template, order)
        return self._send(
            order.customer.phone_normalized, 
            message, 
            'order_created',
            order=order
        )

    def send_order_confirmed(self, order) -> dict:
        """Notifica confirmação do pedido."""
        template = getattr(self.settings, 'msg_order_confirmed', None) or (
            "Olá {nome}! ✅\n\n"
            "Seu pedido *{codigo}* foi confirmado!\n\n"
            "_{loja}_"
        )
        message = self._format_message(template, order)
        return self._send(
            order.customer.phone_normalized, 
            message, 
            'order_confirmed',
            order=order
        )

    # ==================== PAGAMENTO ====================

    def send_payment_received(self, order) -> dict:
        """Notifica pagamento recebido."""
        template = getattr(self.settings, 'msg_payment_received', None) or (
            "Olá {nome}! 💰\n\n"
            "Pagamento do pedido *{codigo}* confirmado!\n"
            "Valor: R$ {valor}\n\n"
            "_{loja}_"
        )
        message = self._format_message(template, order)
        return self._send(
            order.customer.phone_normalized, 
            message, 
            'payment_received',
            order=order
        )

    def send_payment_refunded(self, order) -> dict:
        """Notifica estorno de pagamento."""
        template = getattr(self.settings, 'msg_payment_refunded', None) or (
            "Olá {nome}!\n\n"
            "O valor de R$ {valor} do pedido *{codigo}* foi estornado.\n\n"
            "_{loja}_"
        )
        message = self._format_message(template, order)
        return self._send(
            order.customer.phone_normalized, 
            message, 
            'payment_refunded',
            order=order
        )

    # ==================== ENTREGA ====================

    def send_order_shipped(self, order) -> dict:
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
        return self._send(
            order.customer.phone_normalized, 
            message, 
            'order_shipped',
            order=order
        )

    def send_order_delivered(self, order) -> dict:
        """Notifica entrega do pedido."""
        template = getattr(self.settings, 'msg_order_delivered', None) or (
            "Olá {nome}! ✅\n\n"
            "Seu pedido *{codigo}* foi entregue!\n\n"
            "Obrigado! 😊\n"
            "_{loja}_"
        )
        message = self._format_message(template, order)
        return self._send(
            order.customer.phone_normalized, 
            message, 
            'order_delivered',
            order=order
        )

    def send_delivery_failed(self, order) -> dict:
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
        return self._send(
            order.customer.phone_normalized, 
            message, 
            'delivery_failed',
            order=order
        )

    # ==================== RETIRADA ====================

    def send_order_ready_for_pickup(self, order) -> dict:
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
        return self._send(
            order.customer.phone_normalized, 
            message, 
            'ready_for_pickup',
            order=order
        )

    def send_order_picked_up(self, order) -> dict:
        """Notifica retirada do pedido."""
        template = getattr(self.settings, 'msg_order_picked_up', None) or (
            "Olá {nome}! ✅\n\n"
            "Pedido *{codigo}* retirado!\n\n"
            "Obrigado! 😊\n"
            "_{loja}_"
        )
        message = self._format_message(template, order)
        return self._send(
            order.customer.phone_normalized, 
            message, 
            'picked_up',
            order=order
        )

    def send_order_expired(self, order) -> dict:
        """Notifica expiração do pedido (retirada não realizada)."""
        template = getattr(self.settings, 'msg_order_expired', None) or (
            "Olá {nome}! ⚠️\n\n"
            "O prazo para retirada do pedido *{codigo}* expirou.\n\n"
            "Entre em contato para verificar as opções.\n"
            "_{loja}_"
        )
        message = self._format_message(template, order)
        return self._send(
            order.customer.phone_normalized, 
            message, 
            'expired',
            order=order
        )

    # ==================== CANCELAMENTO ====================

    def send_order_cancelled(self, order) -> dict:
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
        return self._send(
            order.customer.phone_normalized, 
            message, 
            'cancelled',
            order=order
        )

    def send_order_returned(self, order) -> dict:
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
        return self._send(
            order.customer.phone_normalized, 
            message, 
            'returned',
            order=order
        )
