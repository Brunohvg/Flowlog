"""
Services do app orders - Flowlog.
Toda lógica de negócio está aqui. Views são burras.

IMPORTANTE: Todas as notificações WhatsApp são enviadas via transaction.on_commit()
para evitar Race Condition entre o commit do banco e o Celery worker.

SEGURANÇA: Todos os métodos que modificam pedidos usam select_for_update()
para evitar race condition de concorrência (Lost Update).
"""

import logging
import uuid
from datetime import timedelta
from functools import partial

from django.db import transaction as db_transaction
from django.utils import timezone

from apps.integrations.whatsapp.tasks import (
    send_order_created_whatsapp,
    send_order_confirmed_whatsapp,
    send_payment_received_whatsapp,
    send_payment_refunded_whatsapp,
    send_order_shipped_whatsapp,
    send_order_delivered_whatsapp,
    send_delivery_failed_whatsapp,
    send_order_ready_for_pickup_whatsapp,
    send_order_picked_up_whatsapp,
    send_order_expired_whatsapp,
    send_order_cancelled_whatsapp,
    send_order_returned_whatsapp,
)
from apps.orders.models import (
    Customer,
    DeliveryStatus,
    DeliveryType,
    Order,
    OrderActivity,
    OrderStatus,
    PaymentStatus,
)

logger = logging.getLogger("flowlog.orders.services")

# Tempo padrão para expiração de retiradas (48 horas)
PICKUP_EXPIRY_HOURS = 48


def validate_cpf(cpf: str) -> bool:
    """
    Valida CPF usando algoritmo oficial dos dígitos verificadores.
    
    Args:
        cpf: String contendo CPF (com ou sem formatação)
        
    Returns:
        bool: True se CPF é válido
    """
    # Remove caracteres não numéricos
    cpf = ''.join(filter(str.isdigit, cpf))
    
    # CPF deve ter 11 dígitos
    if len(cpf) != 11:
        return False
    
    # Rejeita CPFs com todos os dígitos iguais (ex: 111.111.111-11)
    if cpf == cpf[0] * 11:
        return False
    
    # Calcula primeiro dígito verificador
    soma = sum(int(cpf[i]) * (10 - i) for i in range(9))
    resto = soma % 11
    digito1 = 0 if resto < 2 else 11 - resto
    
    if int(cpf[9]) != digito1:
        return False
    
    # Calcula segundo dígito verificador
    soma = sum(int(cpf[i]) * (11 - i) for i in range(10))
    resto = soma % 11
    digito2 = 0 if resto < 2 else 11 - resto
    
    if int(cpf[10]) != digito2:
        return False
    
    return True


def normalize_cpf(cpf: str) -> str:
    """
    Normaliza CPF removendo formatação.
    
    Args:
        cpf: String contendo CPF
        
    Returns:
        str: CPF apenas com dígitos
    """
    return ''.join(filter(str.isdigit, cpf))


def _safe_send_whatsapp(task, order_id: str, task_name: str = "whatsapp"):
    """
    Envia task do Celery de forma segura.
    Se Redis não estiver disponível, apenas loga e continua.
    
    NOTA: Esta função deve ser chamada DENTRO de transaction.on_commit()
    quando usada dentro de métodos @atomic para evitar Race Condition.
    """
    from django.conf import settings
    
    correlation_id = str(uuid.uuid4())[:8]
    
    # Em modo DEBUG, pula notificações (dev local sem Redis)
    if getattr(settings, 'DEBUG', False):
        logger.debug(
            "WHATSAPP_SKIP | correlation_id=%s | task=%s | order_id=%s | reason=DEBUG_MODE",
            correlation_id, task_name, order_id
        )
        return
    
    # Se não tem broker configurado, pula
    broker_url = getattr(settings, 'CELERY_BROKER_URL', '')
    if not broker_url:
        logger.debug(
            "WHATSAPP_SKIP | correlation_id=%s | task=%s | order_id=%s | reason=NO_BROKER",
            correlation_id, task_name, order_id
        )
        return
    
    try:
        logger.info(
            "CELERY_TASK_DISPATCH | correlation_id=%s | task=%s | order_id=%s | status=sending",
            correlation_id, task_name, order_id
        )
        
        # Envia task com correlation_id nos headers para rastreamento
        result = task.apply_async(
            args=[order_id],
            expires=300,  # 5 minutos para expirar se não processado
            headers={'correlation_id': correlation_id}
        )
        
        logger.info(
            "CELERY_TASK_DISPATCH | correlation_id=%s | task=%s | order_id=%s | "
            "status=dispatched | celery_task_id=%s",
            correlation_id, task_name, order_id, result.id
        )
        
    except Exception as e:
        logger.error(
            "CELERY_TASK_DISPATCH | correlation_id=%s | task=%s | order_id=%s | "
            "status=error | error_type=%s | error=%s",
            correlation_id, task_name, order_id, type(e).__name__, str(e)
        )


def _schedule_whatsapp_after_commit(task, order_id: str, task_name: str):
    """
    Agenda envio de WhatsApp para APÓS o commit da transação.
    Resolve Race Condition entre banco e Celery worker.
    
    Uso:
        _schedule_whatsapp_after_commit(send_order_created_whatsapp, str(order.id), "order_created")
    """
    db_transaction.on_commit(
        partial(_safe_send_whatsapp, task, order_id, task_name)
    )
    logger.debug(
        "WHATSAPP_SCHEDULED | task=%s | order_id=%s | status=waiting_commit",
        task_name, order_id
    )


class OrderService:
    """
    Service responsável pela criação de pedidos.
    """

    @db_transaction.atomic
    def create_order(self, *, tenant, seller, data):
        """
        Cria um novo pedido.
        """
        correlation_id = str(uuid.uuid4())[:8]
        
        logger.info(
            "ORDER_CREATE_START | correlation_id=%s | tenant=%s | seller=%s",
            correlation_id, tenant.id, seller.email
        )
        
        if seller.tenant_id != tenant.id:
            logger.warning(
                "ORDER_CREATE_FAILED | correlation_id=%s | error=tenant_mismatch",
                correlation_id
            )
            raise ValueError("Usuário não pertence ao tenant.")

        # Normalização do telefone
        phone = data["customer_phone"]
        phone_normalized = "".join(filter(str.isdigit, phone))
        
        # CPF opcional - valida se fornecido
        cpf = data.get("customer_cpf", "")
        if cpf:
            cpf = normalize_cpf(cpf)
            if cpf and not validate_cpf(cpf):
                logger.warning(
                    "ORDER_CREATE_FAILED | correlation_id=%s | error=invalid_cpf",
                    correlation_id
                )
                raise ValueError("CPF inválido. Verifique os dígitos informados.")

        # Cliente único por tenant + telefone
        customer, created = Customer.objects.get_or_create(
            tenant=tenant,
            phone_normalized=phone_normalized,
            defaults={
                "name": data["customer_name"],
                "phone": phone,
                "cpf": cpf,
            },
        )
        
        if created:
            logger.info(
                "CUSTOMER_CREATED | correlation_id=%s | customer_id=%s | phone=***%s",
                correlation_id, customer.id, phone_normalized[-4:]
            )
        
        # Se cliente já existia, atualiza nome e CPF se fornecidos
        if not created:
            updated = False
            if data["customer_name"] and data["customer_name"] != customer.name:
                customer.name = data["customer_name"]
                updated = True
            if cpf and not customer.cpf:
                customer.cpf = cpf
                updated = True
            if updated:
                customer.save()
        
        # Verificar se cliente está bloqueado
        if customer.is_blocked:
            logger.warning(
                "ORDER_CREATE_FAILED | correlation_id=%s | error=customer_blocked | customer_id=%s",
                correlation_id, customer.id
            )
            raise ValueError("Este cliente está bloqueado e não pode fazer pedidos.")

        # Tipo de entrega
        delivery_type = data.get("delivery_type", DeliveryType.MOTOBOY)

        # Validação: retirada NÃO tem endereço
        if delivery_type == DeliveryType.PICKUP:
            delivery_address = ""
        else:
            delivery_address = data.get("delivery_address", "")
            if not delivery_address.strip():
                raise ValueError("Endereço de entrega é obrigatório para este tipo de envio.")

        # Criação do pedido
        order = Order.objects.create(
            tenant=tenant,
            customer=customer,
            seller=seller,
            total_value=data["total_value"],
            delivery_type=delivery_type,
            delivery_status=DeliveryStatus.PENDING,
            delivery_address=delivery_address,
            notes=data.get("notes", ""),
            is_priority=data.get("is_priority", False),
        )

        # Log de atividade
        OrderActivity.log(
            order=order,
            activity_type=OrderActivity.ActivityType.CREATED,
            description=f"Pedido criado por {seller.get_full_name() or seller.email}",
            user=seller,
            delivery_type=delivery_type,
            total_value=str(order.total_value),
        )

        logger.info(
            "ORDER_CREATE_SUCCESS | correlation_id=%s | order_code=%s | order_id=%s | "
            "delivery_type=%s | customer=%s | value=%s",
            correlation_id, order.code, order.id, delivery_type, 
            customer.name, order.total_value
        )

        # 🔔 WhatsApp - APÓS COMMIT para evitar Race Condition
        _schedule_whatsapp_after_commit(
            send_order_created_whatsapp, str(order.id), "order_created"
        )

        return order

    @db_transaction.atomic
    def duplicate_order(self, *, order: Order, actor):
        """
        Duplica um pedido existente.
        """
        correlation_id = str(uuid.uuid4())[:8]
        
        logger.info(
            "ORDER_DUPLICATE_START | correlation_id=%s | original_order=%s | actor=%s",
            correlation_id, order.code, actor.email
        )
        
        if order.tenant_id != actor.tenant_id:
            raise ValueError("Usuário não pertence ao tenant do pedido.")

        new_order = Order.objects.create(
            tenant=order.tenant,
            customer=order.customer,
            seller=actor,
            total_value=order.total_value,
            delivery_type=order.delivery_type,
            delivery_status=DeliveryStatus.PENDING,
            delivery_address=order.delivery_address,
            notes=f"Cópia de {order.code}",
        )

        OrderActivity.log(
            order=new_order,
            activity_type=OrderActivity.ActivityType.CREATED,
            description=f"Pedido duplicado de {order.code}",
            user=actor,
            original_order=order.code,
        )

        logger.info(
            "ORDER_DUPLICATE_SUCCESS | correlation_id=%s | original=%s | new=%s",
            correlation_id, order.code, new_order.code
        )

        # 🔔 WhatsApp - APÓS COMMIT
        _schedule_whatsapp_after_commit(
            send_order_created_whatsapp, str(new_order.id), "order_created"
        )

        return new_order


class OrderStatusService:
    """
    Service responsável por mudanças de status do pedido.
    """

    @db_transaction.atomic
    def mark_as_paid(self, *, order: Order, actor):
        """Marca pedido como pago."""
        correlation_id = str(uuid.uuid4())[:8]
        
        logger.info(
            "ORDER_PAYMENT_START | correlation_id=%s | order=%s | actor=%s",
            correlation_id, order.code, actor.email
        )
        
        if order.tenant_id != actor.tenant_id:
            raise ValueError("Usuário não pertence ao tenant do pedido.")

        # Lock da linha para evitar race condition de concorrência
        order = Order.objects.select_for_update().get(id=order.id)

        if order.payment_status == PaymentStatus.PAID:
            logger.info(
                "ORDER_PAYMENT_SKIP | correlation_id=%s | order=%s | reason=already_paid",
                correlation_id, order.code
            )
            return order

        old_status = order.payment_status
        order.payment_status = PaymentStatus.PAID

        if order.order_status == OrderStatus.PENDING:
            order.order_status = OrderStatus.CONFIRMED

        order.save(update_fields=["payment_status", "order_status", "updated_at"])

        OrderActivity.log(
            order=order,
            activity_type=OrderActivity.ActivityType.PAYMENT_RECEIVED,
            description="Pagamento confirmado",
            user=actor,
            old_status=old_status,
        )

        logger.info(
            "ORDER_PAYMENT_SUCCESS | correlation_id=%s | order=%s | old_status=%s",
            correlation_id, order.code, old_status
        )
        
        # 🔔 WhatsApp - APÓS COMMIT
        _schedule_whatsapp_after_commit(
            send_payment_received_whatsapp, str(order.id), "payment_received"
        )
        
        return order

    @db_transaction.atomic
    def mark_as_shipped(self, *, order: Order, actor, tracking_code: str = None):
        """Marca pedido como enviado."""
        correlation_id = str(uuid.uuid4())[:8]
        
        logger.info(
            "ORDER_SHIP_START | correlation_id=%s | order=%s | tracking=%s",
            correlation_id, order.code, tracking_code or "N/A"
        )
        
        if order.tenant_id != actor.tenant_id:
            raise ValueError("Usuário não pertence ao tenant do pedido.")

        # Lock da linha para evitar race condition de concorrência
        order = Order.objects.select_for_update().get(id=order.id)

        if not DeliveryType.is_delivery(order.delivery_type):
            raise ValueError("Pedido de retirada não pode ser enviado.")

        if order.order_status in [OrderStatus.CANCELLED, OrderStatus.RETURNED]:
            raise ValueError("Pedido cancelado/devolvido não pode ser enviado.")

        if order.delivery_status == DeliveryStatus.SHIPPED:
            return order

        if order.delivery_status not in [DeliveryStatus.PENDING, DeliveryStatus.FAILED_ATTEMPT]:
            raise ValueError("Pedido não está em status válido para envio.")

        if DeliveryType.requires_tracking(order.delivery_type):
            if not tracking_code or not tracking_code.strip():
                raise ValueError(f"Código de rastreio é obrigatório para {order.get_delivery_type_display()}.")
            order.tracking_code = tracking_code.strip().upper()
        elif tracking_code:
            order.tracking_code = tracking_code.strip().upper()

        order.delivery_status = DeliveryStatus.SHIPPED
        order.shipped_at = timezone.now()

        if order.order_status == OrderStatus.PENDING:
            order.order_status = OrderStatus.CONFIRMED

        order.save(update_fields=[
            "delivery_status", "shipped_at", "tracking_code", "order_status", "updated_at"
        ])

        OrderActivity.log(
            order=order,
            activity_type=OrderActivity.ActivityType.SHIPPED,
            description=f"Pedido enviado{f' - Rastreio: {order.tracking_code}' if order.tracking_code else ''}",
            user=actor,
            tracking_code=order.tracking_code,
        )

        logger.info(
            "ORDER_SHIP_SUCCESS | correlation_id=%s | order=%s | tracking=%s",
            correlation_id, order.code, order.tracking_code or "N/A"
        )

        # 🔔 WhatsApp - APÓS COMMIT
        _schedule_whatsapp_after_commit(
            send_order_shipped_whatsapp, str(order.id), "order_shipped"
        )
        
        return order

    @db_transaction.atomic
    def mark_as_delivered(self, *, order: Order, actor):
        """Marca pedido como entregue."""
        correlation_id = str(uuid.uuid4())[:8]
        
        logger.info(
            "ORDER_DELIVER_START | correlation_id=%s | order=%s",
            correlation_id, order.code
        )
        
        if order.tenant_id != actor.tenant_id:
            raise ValueError("Usuário não pertence ao tenant do pedido.")

        # Lock da linha para evitar race condition de concorrência
        order = Order.objects.select_for_update().get(id=order.id)

        if not DeliveryType.is_delivery(order.delivery_type):
            raise ValueError("Pedido de retirada não pode ser marcado como entregue.")

        if order.delivery_status == DeliveryStatus.DELIVERED:
            return order

        if order.delivery_status not in [DeliveryStatus.SHIPPED, DeliveryStatus.FAILED_ATTEMPT]:
            raise ValueError("Pedido precisa estar enviado para ser entregue.")

        order.delivery_status = DeliveryStatus.DELIVERED
        order.delivered_at = timezone.now()
        order.order_status = OrderStatus.COMPLETED

        order.save(update_fields=["delivery_status", "delivered_at", "order_status", "updated_at"])

        OrderActivity.log(
            order=order,
            activity_type=OrderActivity.ActivityType.DELIVERED,
            description="Pedido entregue ao cliente",
            user=actor,
        )

        logger.info(
            "ORDER_DELIVER_SUCCESS | correlation_id=%s | order=%s",
            correlation_id, order.code
        )

        # 🔔 WhatsApp - APÓS COMMIT
        _schedule_whatsapp_after_commit(
            send_order_delivered_whatsapp, str(order.id), "order_delivered"
        )
        
        return order

    @db_transaction.atomic
    def mark_failed_attempt(self, *, order: Order, actor, reason: str = ""):
        """Marca tentativa de entrega falha."""
        correlation_id = str(uuid.uuid4())[:8]
        
        logger.info(
            "ORDER_DELIVERY_FAILED_START | correlation_id=%s | order=%s | attempt=%d",
            correlation_id, order.code, order.delivery_attempts + 1
        )
        
        if order.tenant_id != actor.tenant_id:
            raise ValueError("Usuário não pertence ao tenant do pedido.")

        # Lock da linha para evitar race condition de concorrência
        order = Order.objects.select_for_update().get(id=order.id)

        if order.delivery_status != DeliveryStatus.SHIPPED:
            raise ValueError("Pedido precisa estar enviado.")

        order.delivery_status = DeliveryStatus.FAILED_ATTEMPT
        order.delivery_attempts += 1

        order.save(update_fields=["delivery_status", "delivery_attempts", "updated_at"])

        OrderActivity.log(
            order=order,
            activity_type=OrderActivity.ActivityType.FAILED_ATTEMPT,
            description=f"Tentativa {order.delivery_attempts} de entrega falha. {reason}".strip(),
            user=actor,
            attempt_number=order.delivery_attempts,
            reason=reason,
        )

        logger.info(
            "ORDER_DELIVERY_FAILED_SUCCESS | correlation_id=%s | order=%s | attempt=%d",
            correlation_id, order.code, order.delivery_attempts
        )
        
        # 🔔 WhatsApp - APÓS COMMIT
        _schedule_whatsapp_after_commit(
            send_delivery_failed_whatsapp, str(order.id), "delivery_failed"
        )
        
        return order

    @db_transaction.atomic
    def mark_ready_for_pickup(self, *, order: Order, actor):
        """Marca pedido como pronto para retirada."""
        correlation_id = str(uuid.uuid4())[:8]
        
        logger.info(
            "ORDER_READY_PICKUP_START | correlation_id=%s | order=%s",
            correlation_id, order.code
        )
        
        if order.tenant_id != actor.tenant_id:
            raise ValueError("Usuário não pertence ao tenant do pedido.")

        # Lock da linha para evitar race condition de concorrência
        order = Order.objects.select_for_update().get(id=order.id)

        if order.delivery_type != DeliveryType.PICKUP:
            raise ValueError("Apenas pedidos de retirada podem usar esta ação.")

        if order.order_status in [OrderStatus.CANCELLED, OrderStatus.RETURNED]:
            raise ValueError("Pedido cancelado/devolvido.")

        if order.delivery_status == DeliveryStatus.READY_FOR_PICKUP:
            return order

        if order.delivery_status != DeliveryStatus.PENDING:
            raise ValueError("Pedido não está pendente.")

        # Gera código de retirada de 4 dígitos
        order.pickup_code = order.generate_pickup_code()
        
        order.delivery_status = DeliveryStatus.READY_FOR_PICKUP
        order.shipped_at = timezone.now()
        # Define expiração em 48 horas
        order.expires_at = timezone.now() + timedelta(hours=PICKUP_EXPIRY_HOURS)

        if order.order_status == OrderStatus.PENDING:
            order.order_status = OrderStatus.CONFIRMED

        order.save(update_fields=[
            "delivery_status", "shipped_at", "expires_at", "order_status", 
            "pickup_code", "updated_at"
        ])

        OrderActivity.log(
            order=order,
            activity_type=OrderActivity.ActivityType.READY_PICKUP,
            description=f"Pedido pronto para retirada. Código: {order.pickup_code}. Expira em {PICKUP_EXPIRY_HOURS}h.",
            user=actor,
            pickup_code=order.pickup_code,
            expires_at=order.expires_at.isoformat(),
        )

        logger.info(
            "ORDER_READY_PICKUP_SUCCESS | correlation_id=%s | order=%s | pickup_code=%s | expires=%s",
            correlation_id, order.code, order.pickup_code, order.expires_at
        )

        # 🔔 WhatsApp - APÓS COMMIT
        _schedule_whatsapp_after_commit(
            send_order_ready_for_pickup_whatsapp, str(order.id), "ready_for_pickup"
        )
        
        return order

    @db_transaction.atomic
    def mark_as_picked_up(self, *, order: Order, actor):
        """Marca pedido como retirado."""
        correlation_id = str(uuid.uuid4())[:8]
        
        logger.info(
            "ORDER_PICKED_UP_START | correlation_id=%s | order=%s",
            correlation_id, order.code
        )
        
        if order.tenant_id != actor.tenant_id:
            raise ValueError("Usuário não pertence ao tenant do pedido.")

        # Lock da linha para evitar race condition de concorrência
        order = Order.objects.select_for_update().get(id=order.id)

        if order.delivery_type != DeliveryType.PICKUP:
            raise ValueError("Apenas pedidos de retirada podem usar esta ação.")

        if order.delivery_status == DeliveryStatus.PICKED_UP:
            return order

        if order.delivery_status != DeliveryStatus.READY_FOR_PICKUP:
            raise ValueError("Pedido precisa estar pronto para retirada.")

        order.delivery_status = DeliveryStatus.PICKED_UP
        order.delivered_at = timezone.now()
        order.order_status = OrderStatus.COMPLETED
        order.expires_at = None  # Limpa expiração

        order.save(update_fields=[
            "delivery_status", "delivered_at", "order_status", "expires_at", "updated_at"
        ])

        OrderActivity.log(
            order=order,
            activity_type=OrderActivity.ActivityType.PICKED_UP,
            description="Pedido retirado pelo cliente",
            user=actor,
        )

        logger.info(
            "ORDER_PICKED_UP_SUCCESS | correlation_id=%s | order=%s",
            correlation_id, order.code
        )

        # 🔔 WhatsApp - APÓS COMMIT
        _schedule_whatsapp_after_commit(
            send_order_picked_up_whatsapp, str(order.id), "picked_up"
        )
        
        return order

    @db_transaction.atomic
    def cancel_order(self, *, order: Order, actor, reason: str = ""):
        """Cancela um pedido."""
        correlation_id = str(uuid.uuid4())[:8]
        
        logger.info(
            "ORDER_CANCEL_START | correlation_id=%s | order=%s | reason=%s",
            correlation_id, order.code, reason or "N/A"
        )
        
        if order.tenant_id != actor.tenant_id:
            raise ValueError("Usuário não pertence ao tenant do pedido.")

        # Lock da linha para evitar race condition de concorrência
        order = Order.objects.select_for_update().get(id=order.id)

        if order.order_status == OrderStatus.CANCELLED:
            return order

        if order.order_status == OrderStatus.RETURNED:
            raise ValueError("Pedido devolvido não pode ser cancelado.")

        old_status = order.order_status
        order.order_status = OrderStatus.CANCELLED
        order.cancel_reason = reason
        order.cancelled_at = timezone.now()

        order.save(update_fields=[
            "order_status", "cancel_reason", "cancelled_at", "updated_at"
        ])

        OrderActivity.log(
            order=order,
            activity_type=OrderActivity.ActivityType.CANCELLED,
            description=f"Pedido cancelado. {reason}".strip(),
            user=actor,
            old_status=old_status,
            reason=reason,
        )

        logger.info(
            "ORDER_CANCEL_SUCCESS | correlation_id=%s | order=%s | old_status=%s",
            correlation_id, order.code, old_status
        )
        
        # 🔔 WhatsApp - APÓS COMMIT
        _schedule_whatsapp_after_commit(
            send_order_cancelled_whatsapp, str(order.id), "cancelled"
        )
        
        return order

    @db_transaction.atomic
    def return_order(self, *, order: Order, actor, reason: str = "", refund: bool = False):
        """Processa devolução de um pedido."""
        correlation_id = str(uuid.uuid4())[:8]
        
        logger.info(
            "ORDER_RETURN_START | correlation_id=%s | order=%s | refund=%s",
            correlation_id, order.code, refund
        )
        
        if order.tenant_id != actor.tenant_id:
            raise ValueError("Usuário não pertence ao tenant do pedido.")

        # Lock da linha para evitar race condition de concorrência
        order = Order.objects.select_for_update().get(id=order.id)

        if order.order_status != OrderStatus.COMPLETED:
            raise ValueError("Apenas pedidos concluídos podem ser devolvidos.")

        if order.delivery_status not in [DeliveryStatus.DELIVERED, DeliveryStatus.PICKED_UP]:
            raise ValueError("Pedido precisa ter sido entregue/retirado.")

        order.order_status = OrderStatus.RETURNED
        order.return_reason = reason
        order.returned_at = timezone.now()

        if refund and order.payment_status == PaymentStatus.PAID:
            order.payment_status = PaymentStatus.REFUNDED

        order.save(update_fields=[
            "order_status", "return_reason", "returned_at", "payment_status", "updated_at"
        ])

        OrderActivity.log(
            order=order,
            activity_type=OrderActivity.ActivityType.RETURNED,
            description=f"Pedido devolvido. {reason}".strip(),
            user=actor,
            reason=reason,
            refunded=refund,
        )

        if refund:
            OrderActivity.log(
                order=order,
                activity_type=OrderActivity.ActivityType.REFUNDED,
                description="Reembolso processado",
                user=actor,
            )
            # 🔔 WhatsApp - notifica estorno APÓS COMMIT
            _schedule_whatsapp_after_commit(
                send_payment_refunded_whatsapp, str(order.id), "payment_refunded"
            )

        logger.info(
            "ORDER_RETURN_SUCCESS | correlation_id=%s | order=%s | refund=%s",
            correlation_id, order.code, refund
        )
        
        # 🔔 WhatsApp - notifica devolução APÓS COMMIT
        _schedule_whatsapp_after_commit(
            send_order_returned_whatsapp, str(order.id), "returned"
        )
        
        return order

    @db_transaction.atomic
    def change_delivery_type(self, *, order: Order, actor, new_type: str, address: str = ""):
        """Altera o tipo de entrega do pedido."""
        correlation_id = str(uuid.uuid4())[:8]
        
        logger.info(
            "ORDER_DELIVERY_TYPE_CHANGE_START | correlation_id=%s | order=%s | "
            "old_type=%s | new_type=%s",
            correlation_id, order.code, order.delivery_type, new_type
        )
        
        if order.tenant_id != actor.tenant_id:
            raise ValueError("Usuário não pertence ao tenant do pedido.")

        # Lock da linha para evitar race condition de concorrência
        order = Order.objects.select_for_update().get(id=order.id)

        if not order.can_change_delivery_type:
            raise ValueError("Não é possível alterar o tipo de entrega neste momento.")

        old_type = order.delivery_type

        # Validações
        if new_type == DeliveryType.PICKUP:
            address = ""
        elif DeliveryType.requires_address(new_type) and not address.strip():
            raise ValueError("Endereço é obrigatório para este tipo de entrega.")

        # Se estava pronto para retirada e mudou para entrega, volta para pendente
        if order.delivery_status == DeliveryStatus.READY_FOR_PICKUP and new_type != DeliveryType.PICKUP:
            order.delivery_status = DeliveryStatus.PENDING
            order.expires_at = None

        order.delivery_type = new_type
        order.delivery_address = address
        order.tracking_code = ""  # Limpa rastreio antigo

        order.save(update_fields=[
            "delivery_type", "delivery_address", "tracking_code", "delivery_status", "expires_at", "updated_at"
        ])

        OrderActivity.log(
            order=order,
            activity_type=OrderActivity.ActivityType.DELIVERY_TYPE_CHANGED,
            description=f"Tipo de entrega alterado de {dict(DeliveryType.choices)[old_type]} para {dict(DeliveryType.choices)[new_type]}",
            user=actor,
            old_type=old_type,
            new_type=new_type,
        )

        logger.info(
            "ORDER_DELIVERY_TYPE_CHANGE_SUCCESS | correlation_id=%s | order=%s | "
            "%s -> %s",
            correlation_id, order.code, old_type, new_type
        )
        
        return order

    @db_transaction.atomic
    def expire_pickup_order(self, *, order: Order):
        """Expira pedido de retirada não realizada (chamado por task)."""
        correlation_id = str(uuid.uuid4())[:8]
        
        # Lock da linha para evitar race condition de concorrência
        order = Order.objects.select_for_update().get(id=order.id)
        
        if order.delivery_type != DeliveryType.PICKUP:
            return order

        if order.delivery_status != DeliveryStatus.READY_FOR_PICKUP:
            return order

        if not order.expires_at or timezone.now() < order.expires_at:
            return order

        logger.info(
            "ORDER_EXPIRE_START | correlation_id=%s | order=%s | expires_at=%s",
            correlation_id, order.code, order.expires_at
        )

        order.delivery_status = DeliveryStatus.EXPIRED
        order.order_status = OrderStatus.CANCELLED
        order.cancel_reason = "Retirada não realizada no prazo"
        order.cancelled_at = timezone.now()

        order.save(update_fields=[
            "delivery_status", "order_status", "cancel_reason", "cancelled_at", "updated_at"
        ])

        OrderActivity.log(
            order=order,
            activity_type=OrderActivity.ActivityType.EXPIRED,
            description=f"Pedido expirado - retirada não realizada em {PICKUP_EXPIRY_HOURS}h",
            user=None,
        )

        logger.info(
            "ORDER_EXPIRE_SUCCESS | correlation_id=%s | order=%s",
            correlation_id, order.code
        )
        
        return order

    def resend_notification(self, *, order: Order, notification_type: str):
        """
        Reenvia notificação WhatsApp.
        
        NOTA: Este método NÃO está dentro de @atomic, então não precisa de on_commit.
        """
        correlation_id = str(uuid.uuid4())[:8]
        
        logger.info(
            "NOTIFICATION_RESEND_START | correlation_id=%s | order=%s | type=%s",
            correlation_id, order.code, notification_type
        )
        
        if order.order_status in [OrderStatus.CANCELLED, OrderStatus.RETURNED]:
            if notification_type not in ["cancelled", "returned"]:
                raise ValueError("Não é possível enviar notificação para pedido cancelado/devolvido.")

        notification_tasks = {
            "created": send_order_created_whatsapp,
            "confirmed": send_order_confirmed_whatsapp,
            "payment": send_payment_received_whatsapp,
            "shipped": send_order_shipped_whatsapp,
            "delivered": send_order_delivered_whatsapp,
            "ready_pickup": send_order_ready_for_pickup_whatsapp,
            "picked_up": send_order_picked_up_whatsapp,
            "cancelled": send_order_cancelled_whatsapp,
            "returned": send_order_returned_whatsapp,
        }
        
        task = notification_tasks.get(notification_type)
        if not task:
            raise ValueError(f"Tipo de notificação inválido: {notification_type}")
        
        # Resend não está em transação, pode enviar direto
        _safe_send_whatsapp(task, str(order.id), notification_type)

        OrderActivity.log(
            order=order,
            activity_type=OrderActivity.ActivityType.NOTIFICATION_SENT,
            description=f"Notificação reenviada: {notification_type}",
            user=None,
            notification_type=notification_type,
        )

        logger.info(
            "NOTIFICATION_RESEND_SUCCESS | correlation_id=%s | order=%s | type=%s",
            correlation_id, order.code, notification_type
        )
