"""
Serviços de integração com a Mandaê.

Inclui:
- Cliente para API da Mandaê
- Processamento de webhooks
- Mapeamento de status
"""

import hashlib
import hmac
import logging
from dataclasses import dataclass
from typing import Optional

import requests
from django.utils import timezone

logger = logging.getLogger(__name__)


@dataclass
class MandaeTrackingEvent:
    """Representa um evento de rastreio da Mandaê."""

    status: str
    description: str
    location: Optional[str]
    occurred_at: str
    raw_data: dict


class MandaeStatusMapper:
    """Mapeia status da Mandaê para status do Flowlog."""

    # Mapeamento de status Mandaê → (DeliveryStatus, notificar?)
    STATUS_MAP = {
        # Coleta
        "COLETADO": ("shipped", True),
        "COLETA_SOLICITADA": ("pending", False),
        "COLETA_AGENDADA": ("pending", False),

        # Trânsito
        "EM_TRANSITO": ("shipped", False),
        "RECEBIDO_CROSS_DOCKING": ("shipped", False),
        "SAIU_PARA_ENTREGA": ("shipped", True),

        # Entrega
        "ENTREGUE": ("delivered", True),

        # Problemas
        "TENTATIVA_FALHA": ("failed_attempt", True),
        "ENDERECO_NAO_LOCALIZADO": ("failed_attempt", True),
        "DESTINATARIO_AUSENTE": ("failed_attempt", True),
        "RECUSADO": ("failed_attempt", True),

        # Devolução
        "DEVOLVIDO": ("pending", True),  # Requer ação manual
        "EM_DEVOLUCAO": ("shipped", True),

        # Cancelamento
        "CANCELADO": ("pending", False),
    }

    @classmethod
    def map_status(cls, mandae_status: str) -> tuple[str, bool]:
        """
        Mapeia status da Mandaê para DeliveryStatus do Flowlog.

        Returns:
            tuple (delivery_status, should_notify)
        """
        return cls.STATUS_MAP.get(mandae_status.upper(), ("pending", False))

    @classmethod
    def should_complete_order(cls, mandae_status: str) -> bool:
        """Verifica se o pedido deve ser marcado como concluído."""
        return mandae_status.upper() == "ENTREGUE"


class MandaeWebhookValidator:
    """Valida assinaturas de webhooks da Mandaê."""

    @staticmethod
    def validate_signature(
        payload: bytes,
        signature: str,
        secret: str,
    ) -> bool:
        """
        Valida a assinatura HMAC-SHA256 do webhook.

        A Mandaê envia a assinatura no header X-Mandae-Signature.
        """
        if not secret:
            logger.warning("Webhook secret não configurado, validação ignorada")
            return True  # Aceita se não há secret configurado

        if not signature:
            logger.warning("Webhook sem assinatura")
            return False

        # Calcular HMAC esperado
        expected = hmac.new(
            secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()

        # Comparação segura (time-constant)
        return hmac.compare_digest(expected, signature)


class MandaeClient:
    """Cliente para API da Mandaê."""

    def __init__(self, api_url: str, token: str, customer_id: str = ""):
        self.api_url = api_url.rstrip("/")
        self.token = token
        self.customer_id = customer_id
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        })

    def get_tracking(self, tracking_code: str) -> Optional[list[MandaeTrackingEvent]]:
        """
        Consulta o rastreio de uma encomenda.

        Returns:
            Lista de eventos de rastreio ou None se erro
        """
        try:
            url = f"{self.api_url}/trackings/{tracking_code}"
            response = self.session.get(url, timeout=10)

            if response.status_code == 404:
                logger.info("Rastreio não encontrado: %s", tracking_code)
                return None

            response.raise_for_status()
            data = response.json()

            events = []
            for event in data.get("events", []):
                events.append(MandaeTrackingEvent(
                    status=event.get("status", ""),
                    description=event.get("description", ""),
                    location=event.get("location"),
                    occurred_at=event.get("occurredAt", ""),
                    raw_data=event,
                ))

            return events

        except Exception as e:
            logger.exception("Erro ao consultar rastreio Mandaê: %s", e)
            return None

    def get_rates(
        self,
        cep_destino: str,
        items: list[dict],
    ) -> Optional[list[dict]]:
        """
        Calcula as taxas de frete da Mandaê.

        Args:
            cep_destino: CEP de destino (8 dígitos)
            items: Lista de itens com peso e dimensões [{weight, quantity, length, width, height}]

        Returns:
            Lista de opções de frete ou None se erro
        """
        try:
            url = f"{self.api_url}/rates"
            payload = {
                "postalCode": cep_destino.replace("-", ""),
                "declaredValue": sum(i.get("value", 0) for i in items),
                "items": [
                    {
                        "weight": item.get("weight", 0.3),
                        "width": item.get("width", 20),
                        "height": item.get("height", 10),
                        "length": item.get("length", 20),
                        "quantity": item.get("quantity", 1),
                    }
                    for item in items
                ],
            }

            response = self.session.post(url, json=payload, timeout=15)
            response.raise_for_status()
            data = response.json()

            return data.get("shippingServices", [])

        except Exception as e:
            logger.exception("Erro ao calcular frete Mandaê: %s", e)
            return None

    def create_shipment(
        self,
        recipient_name: str,
        recipient_phone: str,
        address: dict,
        items: list[dict],
        order_id: str,
    ) -> Optional[dict]:
        """
        Cria uma nova remessa na Mandaê.
        """
        try:
            payload = {
                "customerId": self.customer_id,
                "scheduling": {
                    "type": "NEXT_BUSINESS_DAY",
                },
                "items": [
                    {
                        "recipient": {
                            "fullName": recipient_name,
                            "phone": recipient_phone,
                        },
                        "destination": {
                            "postalCode": address.get("cep", "").replace("-", ""),
                            "address": address.get("street", ""),
                            "number": address.get("number", "S/N"),
                            "complement": address.get("complement", ""),
                            "neighborhood": address.get("neighborhood", ""),
                            "city": address.get("city", ""),
                            "state": address.get("state", ""),
                        },
                        "partnerItemId": order_id,
                        "skus": [
                            {
                                "description": item.get("description", "Produto"),
                                "quantity": item.get("quantity", 1),
                                "price": item.get("value", 0),
                            }
                            for item in items
                        ],
                    }
                ],
            }

            url = f"{self.api_url}/orders"
            response = self.session.post(url, json=payload, timeout=30)
            response.raise_for_status()

            return response.json()

        except Exception as e:
            logger.exception("Erro ao criar remessa Mandaê: %s", e)
            return None


def process_mandae_webhook(payload: dict, tenant) -> dict:
    """
    Processa um webhook recebido da Mandaê.

    Args:
        payload: Dados do webhook
        tenant: Tenant associado

    Returns:
        Dict com resultado do processamento
    """
    from apps.orders.models import Order, DeliveryStatus, DeliveryType
    from apps.orders.services import OrderStatusService

    result = {
        "processed": False,
        "order_code": None,
        "new_status": None,
        "message": "",
    }

    try:
        # Extrair dados do webhook
        tracking_code = payload.get("trackingCode") or payload.get("tracking_code")
        mandae_status = payload.get("status", "")
        event_data = payload.get("event", {})

        if not tracking_code:
            result["message"] = "Código de rastreio não informado"
            return result

        # Buscar pedido pelo código de rastreio
        try:
            order = Order.objects.get(
                tenant=tenant,
                tracking_code=tracking_code,
                delivery_type=DeliveryType.MANDAE,
            )
        except Order.DoesNotExist:
            result["message"] = f"Pedido não encontrado para rastreio: {tracking_code}"
            return result

        result["order_code"] = order.code

        # Mapear status
        new_delivery_status, should_notify = MandaeStatusMapper.map_status(mandae_status)
        result["new_status"] = new_delivery_status

        # Atualizar status de rastreio
        order.last_tracking_status = mandae_status
        order.last_tracking_check = timezone.now()
        order.save(update_fields=["last_tracking_status", "last_tracking_check"])

        # Atualizar delivery status se necessário
        current_status = order.delivery_status

        # Só atualiza se for uma progressão (não retrocede)
        status_order = {
            DeliveryStatus.PENDING: 0,
            DeliveryStatus.SHIPPED: 1,
            DeliveryStatus.FAILED_ATTEMPT: 2,
            DeliveryStatus.DELIVERED: 3,
        }

        current_order = status_order.get(current_status, 0)
        new_order = status_order.get(new_delivery_status, 0)

        if new_order > current_order or new_delivery_status == DeliveryStatus.FAILED_ATTEMPT:
            # Usar OrderStatusService para manter consistência
            if new_delivery_status == DeliveryStatus.SHIPPED and current_status == DeliveryStatus.PENDING:
                OrderStatusService.mark_as_shipped(order, notify=should_notify)
            elif new_delivery_status == DeliveryStatus.DELIVERED:
                OrderStatusService.mark_as_delivered(order, notify=should_notify)
            elif new_delivery_status == DeliveryStatus.FAILED_ATTEMPT:
                OrderStatusService.mark_failed_delivery(order, notify=should_notify)

        result["processed"] = True
        result["message"] = f"Status atualizado para {new_delivery_status}"

        logger.info(
            "Webhook Mandaê processado: pedido=%s, status=%s->%s",
            order.code, mandae_status, new_delivery_status
        )

    except Exception as e:
        logger.exception("Erro ao processar webhook Mandaê: %s", e)
        result["message"] = str(e)

    return result
