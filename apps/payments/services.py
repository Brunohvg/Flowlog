"""
Service de integração com Pagar.me API v5
Documentação: https://docs.pagar.me/reference/checkout-link

Usa o endpoint /paymentlinks para criar links de pagamento diretos.
"""

import base64
import logging
import requests
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

logger = logging.getLogger(__name__)

PAGARME_API_URL = "https://api.pagar.me/core/v5"


class PagarmeService:
    """Serviço de integração com Pagar.me v5 - Payment Links"""
    
    def __init__(self, api_key: str):
        """
        Args:
            api_key: Secret Key do Pagar.me - aceita dois formatos:
                     - sk_xxx (será convertido para base64)
                     - Base64 direto (usado como está)
        """
        self.api_key = api_key
        self.session = requests.Session()
        
        # Detecta formato da chave e converte se necessário
        auth_value = self._get_auth_value(api_key)
        
        self.session.headers.update({
            "accept": "application/json",
            "content-type": "application/json",
            "authorization": f"Basic {auth_value}",
        })
    
    def _get_auth_value(self, api_key: str) -> str:
        """
        Converte a API key para o formato correto de autenticação.
        
        Se a chave começa com 'sk_', converte para base64.
        Caso contrário, assume que já está em base64.
        """
        api_key = api_key.strip()
        
        # Se começa com sk_, precisa converter para base64
        if api_key.startswith("sk_"):
            # Basic Auth: base64("sk_xxx:")
            auth_string = f"{api_key}:"
            return base64.b64encode(auth_string.encode()).decode()
        
        # Se já parece ser base64, usa direto
        return api_key
    
    def _request(self, method: str, endpoint: str, data: dict = None) -> dict:
        """Faz requisição à API"""
        url = f"{PAGARME_API_URL}/{endpoint}"
        
        try:
            response = self.session.request(method, url, json=data, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code
            error_text = e.response.text[:500]
            
            logger.error(
                "Pagar.me HTTP Error: %s - %s - %s",
                status_code,
                error_text,
                url
            )
            
            # Mensagens amigáveis por código de erro
            if status_code == 401:
                raise PagarmeError("Chave do Pagar.me inválida. Verifique em Configurações → Pagar.me")
            elif status_code == 403:
                raise PagarmeError("Acesso negado. Verifique as permissões da sua conta Pagar.me")
            elif status_code == 422:
                # Tenta extrair mensagem de erro do Pagar.me
                try:
                    error_data = e.response.json()
                    if "errors" in error_data:
                        error_msgs = [err.get("message", "") for err in error_data.get("errors", [])]
                        if error_msgs:
                            raise PagarmeError(f"Dados inválidos: {', '.join(error_msgs)[:150]}")
                    elif "message" in error_data:
                        raise PagarmeError(f"Erro: {error_data['message'][:150]}")
                except (ValueError, KeyError):
                    pass
                raise PagarmeError("Dados inválidos. Verifique as informações")
            elif status_code >= 500:
                raise PagarmeError("Pagar.me temporariamente indisponível. Tente novamente em alguns minutos")
            else:
                raise PagarmeError(f"Erro ao processar pagamento (código {status_code})")
                
        except requests.exceptions.Timeout:
            logger.error("Pagar.me Timeout: %s", url)
            raise PagarmeError("Tempo limite excedido. Tente novamente")
        except requests.exceptions.ConnectionError:
            logger.error("Pagar.me Connection Error: %s", url)
            raise PagarmeError("Não foi possível conectar ao Pagar.me. Verifique sua conexão")
        except requests.exceptions.RequestException as e:
            logger.error("Pagar.me Request Error: %s", str(e))
            raise PagarmeError("Erro de conexão. Tente novamente")
    
    def create_payment_link(
        self,
        amount_cents: int,
        name: str,
        description: str = "",
        max_installments: int = 1,
        free_installments: int = 1,
        interest_rate: float = 0,
        expires_in_minutes: int = 720,  # 12 horas
        enable_pix: bool = False,
    ) -> dict:
        """
        Cria um link de pagamento usando /paymentlinks
        
        Args:
            amount_cents: Valor em centavos (R$ 100,00 = 10000)
            name: Nome/identificação do link (campo obrigatório)
            description: Descrição do produto/serviço
            max_installments: Máximo de parcelas (1-12)
            free_installments: Parcelas sem juros
            interest_rate: Taxa de juros para parcelamento (ex: 2 = 2%)
            expires_in_minutes: Minutos até expirar (default 720 = 12h)
            enable_pix: Se True, habilita PIX como forma de pagamento
        
        Returns:
            dict com: id, url, status
        """
        
        # Validações
        if max_installments < 1:
            max_installments = 1
        if max_installments > 12:
            max_installments = 12
        if free_installments < 1:
            free_installments = 1
        if free_installments > max_installments:
            free_installments = max_installments
        
        # Formas de pagamento aceitas
        accepted_methods = ["credit_card"]
        if enable_pix:
            accepted_methods.append("pix")
        
        # Monta payload conforme documentação /paymentlinks
        # Usando installments_setup (cálculo automático de parcelas)
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
                        "description": description[:500] if description else f"Pagamento: {name}",
                        "default_quantity": 1,
                    }
                ]
            },
        }
        
        # Adiciona config PIX se habilitado
        if enable_pix:
            payload["payment_settings"]["pix_settings"] = {
                "expires_in": expires_in_minutes * 60,  # Em segundos para PIX
            }
        
        # Faz requisição para /paymentlinks
        result = self._request("POST", "paymentlinks", payload)
        
        # Calcula expiração
        expires_at = timezone.now() + timedelta(minutes=expires_in_minutes)
        
        return {
            "id": result.get("id"),
            "url": result.get("url"),
            "status": result.get("status"),
            "expires_at": expires_at,
            "raw_response": result,
        }
    
    def get_payment_link(self, link_id: str) -> dict:
        """Busca dados de um link de pagamento"""
        return self._request("GET", f"paymentlinks/{link_id}")
    
    def cancel_payment_link(self, link_id: str) -> dict:
        """Cancela um link de pagamento"""
        return self._request("PATCH", f"paymentlinks/{link_id}/cancel")


class PagarmeError(Exception):
    """Erro na integração com Pagar.me"""
    pass


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def create_payment_link_for_order(order, installments: int = 1, created_by=None):
    """
    Cria link de pagamento para um pedido existente
    
    Args:
        order: Instância do Order
        installments: Parcelas (1-12)
        created_by: Usuário que criou
    
    Returns:
        PaymentLink instance
    """
    from apps.payments.models import PaymentLink
    
    # Pega API key do tenant
    settings = getattr(order.tenant, "settings", None)
    if not settings or not settings.pagarme_api_key:
        raise PagarmeError("Chave do Pagar.me não configurada")
    
    # Limita parcelas ao máximo configurado
    max_installments = getattr(settings, "pagarme_max_installments", 3) or 3
    if installments > max_installments:
        installments = max_installments
    
    # Cria serviço
    service = PagarmeService(settings.pagarme_api_key)
    
    # Verifica se PIX está habilitado
    enable_pix = getattr(settings, "pagarme_pix_enabled", False)
    
    # Cria link de pagamento
    result = service.create_payment_link(
        amount_cents=int(order.total_value * 100),
        name=f"Pedido {order.code}",
        description=f"Pagamento do pedido {order.code} - {order.customer.name}",
        max_installments=installments,
        free_installments=installments,  # Todas sem juros
        interest_rate=0,
        expires_in_minutes=720,  # 12 horas
        enable_pix=enable_pix,
    )
    
    # Salva no banco
    payment_link = PaymentLink.objects.create(
        tenant=order.tenant,
        order=order,
        pagarme_order_id=result.get("id", ""),
        pagarme_charge_id="",
        checkout_url=result.get("url", ""),
        amount=order.total_value,
        installments=installments,
        description=f"Pedido {order.code}",
        customer_name=order.customer.name,
        customer_phone=order.customer.phone or "",
        customer_email=order.customer.email or "",
        expires_at=result.get("expires_at"),
        created_by=created_by,
    )
    
    return payment_link


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
    """
    Cria link de pagamento avulso (sem pedido)
    
    Args:
        tenant: Tenant
        amount: Valor em Decimal
        description: Descrição
        customer_name: Nome do cliente
        customer_phone: Telefone (opcional)
        customer_email: Email (opcional)
        installments: Parcelas (1-12)
        created_by: Usuário que criou
    
    Returns:
        PaymentLink instance
    """
    from apps.payments.models import PaymentLink
    
    # Pega API key do tenant
    settings = getattr(tenant, "settings", None)
    if not settings or not settings.pagarme_api_key:
        raise PagarmeError("Chave do Pagar.me não configurada")
    
    # Limita parcelas ao máximo configurado
    max_installments = getattr(settings, "pagarme_max_installments", 3) or 3
    if installments > max_installments:
        installments = max_installments
    
    # Cria serviço
    service = PagarmeService(settings.pagarme_api_key)
    
    # Verifica se PIX está habilitado
    enable_pix = getattr(settings, "pagarme_pix_enabled", False)
    
    # Cria link de pagamento
    result = service.create_payment_link(
        amount_cents=int(amount * 100),
        name=f"{customer_name[:50]} - {description[:40]}",
        description=f"{description} - Cliente: {customer_name}",
        max_installments=installments,
        free_installments=installments,  # Todas sem juros
        interest_rate=0,
        expires_in_minutes=720,  # 12 horas
        enable_pix=enable_pix,
    )
    
    # Salva no banco
    payment_link = PaymentLink.objects.create(
        tenant=tenant,
        order=None,  # Sem pedido vinculado
        pagarme_order_id=result.get("id", ""),
        pagarme_charge_id="",
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
    
    return payment_link
