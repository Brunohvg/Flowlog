"""
Tasks Celery para envio de mensagens via WhatsApp.
Cobre TODOS os status de pedido, pagamento e entrega.

IMPORTANTE: 
- OrderNotFoundError permite retry automático (resolve Race Condition)
- Logging estruturado com correlation_id para rastreamento
"""

import logging
import uuid
from functools import partial

from celery import shared_task
from django.apps import apps
from django.db import transaction

from apps.integrations.whatsapp.services import WhatsAppNotificationService

logger = logging.getLogger("flowlog.whatsapp.tasks")


class OrderNotFoundError(Exception):
    """
    Exceção lançada quando pedido não é encontrado.
    
    Permite que o Celery faça retry automático, resolvendo
    Race Condition entre commit do banco e worker.
    """
    pass


def _get_order(order_id: str, event_name: str, correlation_id: str = None):
    """
    Busca pedido com tratamento de erro que PERMITE RETRY.
    
    IMPORTANTE: Ao invés de silenciar Order.DoesNotExist e retornar None,
    lançamos OrderNotFoundError para que o Celery faça retry.
    Isso resolve Race Condition entre transação e worker.
    
    Args:
        order_id: UUID do pedido
        event_name: Nome do evento (para logging)
        correlation_id: ID de correlação (para rastreamento)
        
    Returns:
        Order: Pedido encontrado
        
    Raises:
        OrderNotFoundError: Se pedido não existe (permite retry)
    """
    Order = apps.get_model("orders", "Order")
    correlation_id = correlation_id or str(uuid.uuid4())[:8]
    
    try:
        order = Order.objects.select_related(
            "customer", 
            "tenant", 
            "tenant__settings"
        ).get(id=order_id)
        
        logger.debug(
            "ORDER_FETCH_SUCCESS | correlation_id=%s | event=%s | "
            "order_id=%s | order_code=%s",
            correlation_id, event_name, order_id, order.code
        )
        
        return order
        
    except Order.DoesNotExist:
        # IMPORTANTE: Lança exceção para permitir retry!
        # Isso resolve a Race Condition onde o worker é mais
        # rápido que o commit da transação.
        logger.warning(
            "ORDER_NOT_FOUND | correlation_id=%s | event=%s | "
            "order_id=%s | action=will_retry",
            correlation_id, event_name, order_id
        )
        raise OrderNotFoundError(
            f"Order {order_id} not found for event {event_name}. "
            "Will retry - may be race condition with transaction commit."
        )


def _process_notification(self, order_id: str, event_name: str, send_method_name: str):
    """
    Processa envio de notificação de forma centralizada.
    
    Args:
        self: Task instance (bound task)
        order_id: UUID do pedido
        event_name: Nome do evento (para logging)
        send_method_name: Nome do método no WhatsAppNotificationService
        
    Returns:
        dict: Resultado do envio
    """
    # Extrai correlation_id dos headers da task (se disponível)
    correlation_id = None
    if hasattr(self.request, 'headers') and self.request.headers:
        correlation_id = self.request.headers.get('correlation_id')
    correlation_id = correlation_id or str(uuid.uuid4())[:8]
    
    task_id = self.request.id or 'unknown'
    retry_count = self.request.retries or 0
    
    logger.info(
        "TASK_START | correlation_id=%s | task_id=%s | event=%s | "
        "order_id=%s | retry=%d",
        correlation_id, task_id, event_name, order_id, retry_count
    )
    
    try:
        # Busca pedido (pode lançar OrderNotFoundError para retry)
        order = _get_order(order_id, event_name, correlation_id)
        
        # Inicializa service
        service = WhatsAppNotificationService(
            order.tenant,
            correlation_id=correlation_id,
            celery_task_id=task_id
        )
        
        # Obtém método de envio
        send_method = getattr(service, send_method_name, None)
        if not send_method:
            logger.error(
                "TASK_ERROR | correlation_id=%s | event=%s | "
                "error=method_not_found | method=%s",
                correlation_id, event_name, send_method_name
            )
            return {"success": False, "error": f"Method {send_method_name} not found"}
        
        # Envia notificação
        result = send_method(order)
        
        if result.get("success"):
            logger.info(
                "TASK_SUCCESS | correlation_id=%s | task_id=%s | event=%s | "
                "order_code=%s | notification_log_id=%s",
                correlation_id, task_id, event_name, 
                order.code, result.get("notification_log_id")
            )
        elif result.get("blocked"):
            logger.info(
                "TASK_BLOCKED | correlation_id=%s | task_id=%s | event=%s | "
                "order_code=%s | reason=%s",
                correlation_id, task_id, event_name,
                order.code, result.get("block_reason", "unknown")
            )
        else:
            logger.warning(
                "TASK_FAILED | correlation_id=%s | task_id=%s | event=%s | "
                "order_code=%s | error=%s",
                correlation_id, task_id, event_name,
                order.code, result.get("error", "unknown")
            )
        
        return result
        
    except OrderNotFoundError:
        # Re-raise para permitir retry automático do Celery
        logger.warning(
            "TASK_RETRY | correlation_id=%s | task_id=%s | event=%s | "
            "order_id=%s | reason=order_not_found | retry=%d",
            correlation_id, task_id, event_name, order_id, retry_count
        )
        raise
        
    except Exception as e:
        logger.exception(
            "TASK_EXCEPTION | correlation_id=%s | task_id=%s | event=%s | "
            "order_id=%s | error_type=%s | error=%s",
            correlation_id, task_id, event_name, order_id,
            type(e).__name__, str(e)
        )
        raise


# ==================== CONFIGURAÇÃO BASE DAS TASKS ====================

# Configuração padrão para todas as tasks de WhatsApp
TASK_CONFIG = {
    "bind": True,
    "autoretry_for": (Exception, OrderNotFoundError),
    "retry_kwargs": {"max_retries": 5, "countdown": 5},
    "retry_backoff": True,
    "retry_backoff_max": 60,  # Máximo 60 segundos entre retries
    "retry_jitter": True,
    "acks_late": True,  # Só confirma após processar (mais seguro)
    "reject_on_worker_lost": True,  # Rejeita se worker morrer
}


# ==================== PEDIDO ====================

@shared_task(**TASK_CONFIG)
def send_order_created_whatsapp(self, order_id):
    """Envia mensagem de pedido criado."""
    return _process_notification(self, order_id, "order_created", "send_order_created")


@shared_task(**TASK_CONFIG)
def send_order_confirmed_whatsapp(self, order_id):
    """Envia mensagem de pedido confirmado."""
    return _process_notification(self, order_id, "order_confirmed", "send_order_confirmed")


# ==================== PAGAMENTO ====================

@shared_task(**TASK_CONFIG)
def send_payment_received_whatsapp(self, order_id):
    """Envia mensagem de pagamento recebido."""
    return _process_notification(self, order_id, "payment_received", "send_payment_received")


@shared_task(**TASK_CONFIG)
def send_payment_refunded_whatsapp(self, order_id):
    """Envia mensagem de estorno de pagamento."""
    return _process_notification(self, order_id, "payment_refunded", "send_payment_refunded")


# ==================== ENTREGA ====================

@shared_task(**TASK_CONFIG)
def send_order_shipped_whatsapp(self, order_id):
    """Envia mensagem de pedido enviado."""
    return _process_notification(self, order_id, "order_shipped", "send_order_shipped")


@shared_task(**TASK_CONFIG)
def send_order_delivered_whatsapp(self, order_id):
    """Envia mensagem de pedido entregue."""
    return _process_notification(self, order_id, "order_delivered", "send_order_delivered")


@shared_task(**TASK_CONFIG)
def send_delivery_failed_whatsapp(self, order_id):
    """Envia mensagem de tentativa de entrega falha."""
    return _process_notification(self, order_id, "delivery_failed", "send_delivery_failed")


# ==================== RETIRADA ====================

@shared_task(**TASK_CONFIG)
def send_order_ready_for_pickup_whatsapp(self, order_id):
    """Envia mensagem de pedido pronto para retirada."""
    return _process_notification(self, order_id, "ready_for_pickup", "send_order_ready_for_pickup")


@shared_task(**TASK_CONFIG)
def send_order_picked_up_whatsapp(self, order_id):
    """Envia mensagem de pedido retirado."""
    return _process_notification(self, order_id, "picked_up", "send_order_picked_up")


@shared_task(**TASK_CONFIG)
def send_order_expired_whatsapp(self, order_id):
    """Envia mensagem de pedido expirado (retirada não realizada)."""
    return _process_notification(self, order_id, "expired", "send_order_expired")


# ==================== CANCELAMENTO ====================

@shared_task(**TASK_CONFIG)
def send_order_cancelled_whatsapp(self, order_id):
    """Envia mensagem de pedido cancelado."""
    return _process_notification(self, order_id, "cancelled", "send_order_cancelled")


@shared_task(**TASK_CONFIG)
def send_order_returned_whatsapp(self, order_id):
    """Envia mensagem de pedido devolvido."""
    return _process_notification(self, order_id, "returned", "send_order_returned")


# ==================== TASKS PERIÓDICAS ====================

@shared_task(bind=True)
def expire_pending_pickups(self):
    """
    Task periódica para expirar pedidos de retirada não realizados.
    Deve ser executada a cada hora via Celery Beat.
    """
    from apps.orders.models import Order, DeliveryStatus, DeliveryType
    from apps.orders.services import OrderStatusService
    from django.utils import timezone
    
    correlation_id = str(uuid.uuid4())[:8]
    task_id = self.request.id or 'unknown'
    
    logger.info(
        "EXPIRE_PICKUPS_START | correlation_id=%s | task_id=%s",
        correlation_id, task_id
    )
    
    # Busca pedidos de retirada que expiraram
    expired_orders = Order.objects.filter(
        delivery_type=DeliveryType.PICKUP,
        delivery_status=DeliveryStatus.READY_FOR_PICKUP,
        expires_at__lt=timezone.now(),
    ).select_related("tenant", "tenant__settings")
    
    service = OrderStatusService()
    success_count = 0
    error_count = 0
    
    for order in expired_orders:
        try:
            logger.info(
                "EXPIRE_ORDER_START | correlation_id=%s | order=%s | expires_at=%s",
                correlation_id, order.code, order.expires_at
            )
            
            service.expire_pickup_order(order=order)
            
            # Agenda notificação WhatsApp APÓS commit
            # Usa on_commit porque expire_pickup_order é @atomic
            transaction.on_commit(
                partial(
                    send_order_expired_whatsapp.delay,
                    str(order.id)
                )
            )
            
            success_count += 1
            
            logger.info(
                "EXPIRE_ORDER_SUCCESS | correlation_id=%s | order=%s",
                correlation_id, order.code
            )
            
        except Exception as e:
            error_count += 1
            logger.exception(
                "EXPIRE_ORDER_ERROR | correlation_id=%s | order=%s | "
                "error_type=%s | error=%s",
                correlation_id, order.code, type(e).__name__, str(e)
            )
    
    logger.info(
        "EXPIRE_PICKUPS_COMPLETE | correlation_id=%s | task_id=%s | "
        "total=%d | success=%d | errors=%d",
        correlation_id, task_id, success_count + error_count,
        success_count, error_count
    )
    
    return {
        "expired": success_count,
        "errors": error_count,
        "total": success_count + error_count
    }


@shared_task(bind=True)
def cleanup_old_notification_logs(self, days: int = 90):
    """
    Task periódica para limpar logs antigos de notificações.
    Deve ser executada diariamente via Celery Beat.
    
    Args:
        days: Número de dias para manter logs (padrão 90)
    """
    from django.utils import timezone
    from datetime import timedelta
    
    correlation_id = str(uuid.uuid4())[:8]
    task_id = self.request.id or 'unknown'
    
    logger.info(
        "CLEANUP_LOGS_START | correlation_id=%s | task_id=%s | days=%d",
        correlation_id, task_id, days
    )
    
    try:
        # Tenta importar os models de log (podem não existir ainda)
        NotificationLog = apps.get_model("integrations", "NotificationLog")
        APIRequestLog = apps.get_model("integrations", "APIRequestLog")
        
        cutoff_date = timezone.now() - timedelta(days=days)
        
        # Deleta logs de notificação antigos
        notification_deleted, _ = NotificationLog.objects.filter(
            created_at__lt=cutoff_date
        ).delete()
        
        # Deleta logs de API antigos
        api_deleted, _ = APIRequestLog.objects.filter(
            created_at__lt=cutoff_date
        ).delete()
        
        logger.info(
            "CLEANUP_LOGS_SUCCESS | correlation_id=%s | task_id=%s | "
            "notification_logs_deleted=%d | api_logs_deleted=%d",
            correlation_id, task_id, notification_deleted, api_deleted
        )
        
        return {
            "notification_logs_deleted": notification_deleted,
            "api_logs_deleted": api_deleted,
        }
        
    except LookupError:
        # Models ainda não existem
        logger.warning(
            "CLEANUP_LOGS_SKIP | correlation_id=%s | reason=models_not_found",
            correlation_id
        )
        return {"skipped": True, "reason": "Log models not found"}
        
    except Exception as e:
        logger.exception(
            "CLEANUP_LOGS_ERROR | correlation_id=%s | error_type=%s | error=%s",
            correlation_id, type(e).__name__, str(e)
        )
        raise
