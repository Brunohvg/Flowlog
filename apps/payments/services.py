"""
Service de integração com Pagar.me API v5
Documentação: https://docs.pagar.me/reference/checkout-link

Usa o endpoint /paymentlinks para criar links de pagamento diretos.
"""

import base64
import logging
from datetime import timedelta
from decimal import Decimal

import requests
from django.utils import timezone

logger = logging.getLogger(__name__)

PAGARME_API_URL = "https://api.pagar.me/core/v5"


class PagarmeService:
    """Serviço de integração com Pagar.me v5 - Payment Links"""

    def __init__(self, api_key: str):
        """
        Args:
            api_key: Secret Key do Pagar.me.
        """
        self.api_key = api_key
        self.session = requests.Session()

        # Detecta formato da chave e converte se necessário
        auth_value = self._get_auth_value(api_key)

        self.session.headers.update(
            {
                "accept": "application/json",
                "content-type": "application/json",
                "authorization": f"Basic {auth_value}",
            }
        )

    def _get_auth_value(self, api_key: str) -> str:
        """Converte a API key para o formato Basic Auth (base64) se necessário."""
        api_key = api_key.strip()
        if api_key.startswith("sk_"):
            auth_string = f"{api_key}:"
            return base64.b64encode(auth_string.encode()).decode()
        return api_key

    def _request(self, method: str, endpoint: str, data: dict = None) -> dict:
        """Faz requisição à API com tratamento de erros."""
        url = f"{PAGARME_API_URL}/{endpoint}"

        try:
            response = self.session.request(method, url, json=data, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code

            # Logs para debug
            try:
                error_text = e.response.json()
            except:
                error_text = e.response.text[:200]

            logger.error("Pagar.me Error [%s]: %s", status_code, error_text)

            if status_code == 401:
                raise PagarmeError("Chave de API inválida.")
            elif status_code == 422:
                raise PagarmeError("Dados inválidos enviados ao Pagar.me.")
            elif status_code >= 500:
                raise PagarmeError("Erro no servidor do Pagar.me.")
            else:
                raise PagarmeError(f"Erro na transação ({status_code}).")

        except requests.exceptions.RequestException as e:
            logger.error("Pagar.me Connection Error: %s", e)
            raise PagarmeError("Falha de conexão com Pagar.me.")

    def create_payment_link(
        self,
        amount_cents: int,
        name: str,
        description: str = "",
        max_installments: int = 1,
        free_installments: int = 1,
        interest_rate: float = 0,
        expires_in_minutes: int = 720,
        enable_pix: bool = False,
    ) -> dict:
        """Cria um link de pagamento."""

        # Validações de parcelas
        max_installments = max(1, min(max_installments, 12))
        free_installments = max(1, min(free_installments, max_installments))

        accepted_methods = ["credit_card"]
        if enable_pix:
            accepted_methods.append("pix")

        payload = {
            "is_building": False,
            "name": name[:100],
            "type": "order",
            "expires_in": expires_in_minutes,
            "max_paid_sessions": 1,
            "payment_settings": {
                "accepted_payment_methods": accepted_methods,
                "credit_card_settings": {
                    "operation_type": "auth_and_capture",
                    "installments_setup": {
                        "interest_type": "simple",
                        "max_installments": max_installments,
                        "amount": amount_cents,
                        "interest_rate": interest_rate,
                        "free_installments": free_installments,
                    },
                },
            },
            "cart_settings": {
                "items": [
                    {
                        "amount": amount_cents,
                        "name": description[:200] if description else name[:200],
                        "description": description[:500] if description else name,
                        "default_quantity": 1,
                    }
                ]
            },
        }

        if enable_pix:
            payload["payment_settings"]["pix_settings"] = {
                "expires_in": expires_in_minutes * 60,
            }

        result = self._request("POST", "paymentlinks", payload)
        expires_at = timezone.now() + timedelta(minutes=expires_in_minutes)

        return {
            "id": result.get("id"),
            "url": result.get("url"),
            "status": result.get("status"),
            "expires_at": expires_at,
            "raw_response": result,
        }

    def get_payment_link(self, link_id: str) -> dict:
        return self._request("GET", f"paymentlinks/{link_id}")

    def cancel_payment_link(self, link_id: str) -> dict:
        return self._request("PATCH", f"paymentlinks/{link_id}/cancel")


class PagarmeError(Exception):
    pass


# ============================================================
# FUNÇÕES AUXILIARES (Factories)
# ============================================================


def create_payment_link_for_order(order, installments: int = 1, created_by=None):
    """Cria PaymentLink vinculado a um Order."""
    from apps.payments.models import PaymentLink

    settings = getattr(order.tenant, "settings", None)
    if not settings or not settings.pagarme_api_key:
        raise PagarmeError("Pagar.me não configurado.")

    max_inst = getattr(settings, "pagarme_max_installments", 3) or 3
    installments = min(installments, max_inst)

    service = PagarmeService(settings.pagarme_api_key)
    enable_pix = getattr(settings, "pagarme_pix_enabled", False)

    # Cria no Pagar.me
    result = service.create_payment_link(
        amount_cents=int(order.total_value * 100),
        name=f"Pedido {order.code}",
        description=f"Pedido {order.code} - {order.customer.name}",
        max_installments=installments,
        free_installments=installments,
        expires_in_minutes=720,  # 12h
        enable_pix=enable_pix,
    )

    # Salva no Banco (Sem os dados do Payer ainda)
    return PaymentLink.objects.create(
        tenant=order.tenant,
        order=order,
        pagarme_order_id=result.get("id", ""),
        checkout_url=result.get("url", ""),
        amount=order.total_value,
        installments=installments,
        description=f"Pedido {order.code}",
        customer_name=order.customer.name,
        customer_phone=order.customer.phone_normalized,
        customer_email=order.customer.email,
        expires_at=result.get("expires_at"),
        created_by=created_by,
    )


def create_standalone_payment_link(
    tenant,
    amount: Decimal,
    description: str,
    customer_name: str,
    customer_phone: str = "",
    customer_email: str = "",
    installments: int = 1,
    created_by=None,
):
    """Cria PaymentLink avulso."""
    from apps.payments.models import PaymentLink

    settings = getattr(tenant, "settings", None)
    if not settings or not settings.pagarme_api_key:
        raise PagarmeError("Pagar.me não configurado.")

    max_inst = getattr(settings, "pagarme_max_installments", 3) or 3
    installments = min(installments, max_inst)

    service = PagarmeService(settings.pagarme_api_key)
    enable_pix = getattr(settings, "pagarme_pix_enabled", False)

    result = service.create_payment_link(
        amount_cents=int(amount * 100),
        name=f"{customer_name[:30]} - {description[:30]}",
        description=description,
        max_installments=installments,
        free_installments=installments,
        expires_in_minutes=720,
        enable_pix=enable_pix,
    )

    return PaymentLink.objects.create(
        tenant=tenant,
        order=None,
        pagarme_order_id=result.get("id", ""),
        checkout_url=result.get("url", ""),
        amount=amount,
        installments=installments,
        description=description,
        customer_name=customer_name,
        customer_phone=customer_phone,
        customer_email=customer_email,
        expires_at=result.get("expires_at"),
        created_by=created_by,
    )
