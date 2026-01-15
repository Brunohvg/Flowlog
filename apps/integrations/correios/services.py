"""
Serviços de integração com os Correios.

Inclui:
- Cliente de autenticação (OAuth/JWT)
- Cliente de rastreamento
- Task de polling
"""

import base64
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import requests
from django.utils import timezone

logger = logging.getLogger(__name__)


@dataclass
class CorreiosToken:
    """Token de autenticação dos Correios."""

    token: str
    expires_at: datetime
    ambiente: str = "PRODUCAO"

    @property
    def is_expired(self) -> bool:
        """Verifica se o token está expirado (com margem de 5 min)."""
        return timezone.now() >= self.expires_at - timedelta(minutes=5)


@dataclass
class CorreiosTrackingEvent:
    """Evento de rastreio dos Correios."""

    status: str
    description: str
    location: str
    occurred_at: datetime
    tipo: str  # Tipo do evento (BDE, BDI, etc.)
    raw_data: dict


class CorreiosAuthClient:
    """
    Cliente de autenticação da API dos Correios.

    Usa Basic Auth (usuario:codigo_acesso) para obter token JWT.
    O token é cacheado no TenantSettings até expiração.
    """

    BASE_URL = "https://api.correios.com.br/token/v1"

    def __init__(self, usuario: str, codigo_acesso: str):
        self.usuario = usuario
        self.codigo_acesso = codigo_acesso

    def _get_basic_auth_header(self) -> str:
        """Gera header Basic Auth."""
        credentials = f"{self.usuario}:{self.codigo_acesso}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"

    def get_token(self, contrato: str = "", cartao: str = "") -> Optional[CorreiosToken]:
        """
        Obtém token de autenticação dos Correios.

        Args:
            contrato: Número do contrato (opcional)
            cartao: Cartão de postagem (opcional)

        Returns:
            CorreiosToken ou None se erro
        """
        try:
            headers = {
                "Authorization": self._get_basic_auth_header(),
                "Content-Type": "application/json",
            }

            # Escolher endpoint baseado nos parâmetros
            if cartao and contrato:
                url = f"{self.BASE_URL}/autentica/cartaopostagem"
                body = {
                    "numero": cartao,
                    "contrato": contrato,
                }
            elif contrato:
                url = f"{self.BASE_URL}/autentica/contrato"
                body = {"numero": contrato}
            else:
                url = f"{self.BASE_URL}/autentica"
                body = None

            if body:
                response = requests.post(url, headers=headers, json=body, timeout=10)
            else:
                response = requests.post(url, headers=headers, timeout=10)

            response.raise_for_status()
            data = response.json()

            # Parse expiração
            expires_str = data.get("expiraEm", "")
            if expires_str:
                # Formato: 2026-01-15T03:00:00Z ou similar
                expires_at = datetime.fromisoformat(expires_str.replace("Z", "+00:00"))
            else:
                # Fallback: 1 hora
                expires_at = timezone.now() + timedelta(hours=1)

            return CorreiosToken(
                token=data.get("token", ""),
                expires_at=expires_at,
                ambiente=data.get("ambiente", "PRODUCAO"),
            )

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                logger.error("Correios: credenciais inválidas")
            else:
                logger.exception("Correios: erro HTTP ao autenticar: %s", e)
            return None
        except Exception as e:
            logger.exception("Correios: erro ao autenticar: %s", e)
            return None


class CorreiosTrackingClient:
    """
    Cliente de rastreamento dos Correios.

    Usa a API SRO (Sistema de Rastreamento de Objetos).
    """

    BASE_URL = "https://api.correios.com.br/srorastro/v1"

    def __init__(self, token: str):
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        })

    def get_tracking(self, tracking_code: str) -> Optional[list[CorreiosTrackingEvent]]:
        """
        Consulta o rastreio de um objeto.

        Args:
            tracking_code: Código de rastreio (ex: SS987654321BR)

        Returns:
            Lista de eventos ou None se erro
        """
        try:
            url = f"{self.BASE_URL}/objetos/{tracking_code}"
            params = {
                "resultado": "T",  # Todos os eventos
            }

            response = self.session.get(url, params=params, timeout=15)

            if response.status_code == 404:
                logger.info("Correios: objeto não encontrado: %s", tracking_code)
                return None

            if response.status_code == 429:
                logger.warning("Correios: rate limit atingido")
                return None

            response.raise_for_status()
            data = response.json()

            objetos = data.get("objetos", [])
            if not objetos:
                return None

            objeto = objetos[0]
            eventos = objeto.get("eventos", [])

            result = []
            for evento in eventos:
                # Parse data
                dt_str = evento.get("dtHrCriado", "")
                if dt_str:
                    occurred_at = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                else:
                    occurred_at = timezone.now()

                # Extrair localização
                unidade = evento.get("unidade", {})
                endereco = unidade.get("endereco", {})
                location = f"{endereco.get('cidade', '')}/{endereco.get('uf', '')}"

                result.append(CorreiosTrackingEvent(
                    status=evento.get("codigo", ""),
                    description=evento.get("descricao", ""),
                    location=location.strip("/"),
                    occurred_at=occurred_at,
                    tipo=evento.get("tipo", ""),
                    raw_data=evento,
                ))

            return result

        except Exception as e:
            logger.exception("Correios: erro ao consultar rastreio: %s", e)
            return None


class CorreiosPricingClient:
    """
    Cliente de cálculo de preços e prazos dos Correios (API CWS).
    Usa a lógica de LOTE (Batch) para calcular múltiplos serviços (SEDEX, PAC) de uma vez.
    Separa chamadas de Preço e Prazo conforme recomendação do usuário.
    """

    URL_PRECO = "https://api.correios.com.br/preco/v1/nacional"
    URL_PRAZO = "https://api.correios.com.br/prazo/v1/nacional"

    # Serviços padrão: 03220 (SEDEX), 03298 (PAC)
    PRODUTOS_DEFAULT = ["03220", "03298"]

    def __init__(self, token: str, contrato: str = "", cartao: str = ""):
        self.token = token
        self.contrato = contrato
        self.cartao = cartao
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    def _consultar_preco(self, payload: dict) -> list:
        try:
            resp = self.session.post(self.URL_PRECO, json=payload, timeout=10)
            if resp.status_code == 401:
                logger.warning("Correios CWS Preco: Unauthorized")
                return []
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error("Correios Preco Error: %s", e)
            return []

    def _consultar_prazo(self, payload: dict) -> list:
        try:
            resp = self.session.post(self.URL_PRAZO, json=payload, timeout=10)
            if resp.status_code == 401:
                logger.warning("Correios CWS Prazo: Unauthorized")
                return []
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error("Correios Prazo Error: %s", e)
            return []

    def calculate_batch(
        self,
        cep_origem: str,
        cep_destino: str,
        peso_gramas: int,
        comprimento: int = 20,
        largura: int = 20,
        altura: int = 20,
        produtos: list = None,
        formato: int = 1
    ) -> dict:
        """
        Calcula preços e prazos em lote.
        Retorna dicionário: {"03220": {"preco": ..., "prazo": ...}, ...}

        Args:
            peso_gramas: Peso em gramas (convertido para float no payload se necessário, mas API aceita string/int)
                         O usuário passou 25000 (25kg) no exemplo, então usamos peso em GRAMAS.
        """

        produtos = produtos or self.PRODUTOS_DEFAULT
        id_lote = "lote-flowlog-001"

        # Garantir CEPs limpos
        cep_origem = cep_origem.replace("-", "")
        cep_destino = cep_destino.replace("-", "")

        # ----- Monta params PREÇO -----
        parametros_preco = []
        for i, produto in enumerate(produtos, start=1):
            item = {
                "coProduto": produto,
                "nuRequisicao": i,
                "cepOrigem": cep_origem,
                "cepDestino": cep_destino,
                "psObjeto": str(peso_gramas), # User code sends float, API often takes string. Let's force proper type. User sample had 25000 int.
                "comprimento": str(int(comprimento)),
                "largura": str(int(largura)),
                "altura": str(int(altura)),
                "nuFormato": formato,
                "tpObjeto": "2", # 2 = Caixa/Pacote
            }

            if self.contrato and self.cartao:
                item["nuContrato"] = self.contrato
                # item["nuDR"] = "0" # Opcional, alguns contratos exigem, outros não.

            parametros_preco.append(item)

        payload_preco = {
            "idLote": id_lote,
            "parametrosProduto": parametros_preco
        }

        # ----- Monta params PRAZO -----
        parametros_prazo = []
        for i, produto in enumerate(produtos, start=1):
            item_prazo = {
                "coProduto": produto,
                "nuRequisicao": i,
                "cepOrigem": cep_origem,
                "cepDestino": cep_destino,
            }
            if self.contrato and self.cartao:
                item_prazo["nuContrato"] = self.contrato

            parametros_prazo.append(item_prazo)

        payload_prazo = {
            "idLote": id_lote,
            "parametrosPrazo": parametros_prazo
        }

        # ----- Chama APIs -----
        # Executar em sequencia (poderia ser paralelo, mas vamos manter simples/seguro)
        preco_resp = self._consultar_preco(payload_preco)
        prazo_resp = self._consultar_prazo(payload_prazo)

        # O retorno é uma LISTA de objetos, ex: [{"coProduto": "...", "pcFinal": "..."}]

        # Indexar por código do produto para facilitar junção
        precos_map = {}
        if isinstance(preco_resp, list):
            for p in preco_resp:
                if "coProduto" in p:
                    precos_map[p["coProduto"]] = p

        prazos_map = {}
        if isinstance(prazo_resp, list):
            for p in prazo_resp:
                if "coProduto" in p:
                    prazos_map[p["coProduto"]] = p

        # ----- Junta retorno organizado -----
        retorno = {}
        for produto in produtos:
            dados_preco = precos_map.get(produto, {})
            dados_prazo = prazos_map.get(produto, {})

            # Extrair valores relevantes
            # Preco
            preco_final = dados_preco.get("pcFinal", "0").replace(",", ".")
            try:
                valor = float(preco_final)
            except:
                valor = 0.0

            msg_erro_preco = dados_preco.get("msgErro", "")

            # Prazo
            prazo_dias = dados_prazo.get("prazoEntrega", "0")
            try:
                dias = int(prazo_dias)
            except:
                dias = 0

            msg_erro_prazo = dados_prazo.get("msgErro", "")

            error = msg_erro_preco or msg_erro_prazo

            retorno[produto] = {
                "price": valor,
                "days": dias,
                "error": error
            }

        return retorno

class CorreiosStatusMapper:
    """Mapeia códigos de evento dos Correios para status do Flowlog."""

    # Mapeamento de códigos para (DeliveryStatus, should_notify)
    STATUS_MAP = {
        # Postado/Coletado
        "PO": ("shipped", True),  # Postado
        "RO": ("shipped", True),  # Objeto recebido dos correios

        # Em trânsito
        "DO": ("shipped", False),  # Objeto em trânsito
        "PAR": ("shipped", False), # Objeto em transferência
        "OEC": ("shipped", True),  # Objeto saiu para entrega

        # Entregue
        "BDE": ("delivered", True),  # Entregue ao destinatário
        "BDI": ("delivered", True),  # Entregue ao destinatário

        # Problemas
        "BDR": ("failed_attempt", True),  # Tentativa de entrega não realizada
        "LDI": ("failed_attempt", True),  # Objeto aguardando retirada
        "OEC-FAILED": ("failed_attempt", True),  # Não foi possível entregar

        # Devolução
        "BLQ": ("pending", True),  # Objeto bloqueado
        "FC": ("pending", True),   # Devolvido ao remetente
    }

    @classmethod
    def map_status(cls, codigo: str) -> tuple[str, bool]:
        """
        Mapeia código de evento para DeliveryStatus.

        Returns:
            tuple (delivery_status, should_notify)
        """
        return cls.STATUS_MAP.get(codigo.upper(), ("shipped", False))

    @classmethod
    def should_complete_order(cls, codigo: str) -> bool:
        """Verifica se o pedido deve ser marcado como concluído."""
        return codigo.upper() in ["BDE", "BDI"]


def get_correios_client(tenant_settings) -> Optional[tuple[CorreiosAuthClient, CorreiosTrackingClient]]:
    """
    Obtém clientes de autenticação e rastreamento configurados.

    Gerencia cache de token no TenantSettings.

    Returns:
        Tuple (auth_client, tracking_client) ou None se não configurado
    """
    if not tenant_settings.correios_enabled:
        return None

    if not tenant_settings.correios_usuario or not tenant_settings.correios_codigo_acesso:
        logger.warning("Correios não configurado completamente")
        return None

    # Verificar token cacheado
    token = None
    if tenant_settings.correios_token:
        # Se for token CWS manual (começa com cws-) ou se tiver data de expiração válida
        is_manual_cws = tenant_settings.correios_token.startswith("cws-")

        if is_manual_cws:
             token = tenant_settings.correios_token
        elif tenant_settings.correios_token_expira and tenant_settings.correios_token_expira > timezone.now() + timedelta(minutes=5):
            token = tenant_settings.correios_token

    if not token:
        # Obter novo token
        auth_client = CorreiosAuthClient(
            usuario=tenant_settings.correios_usuario,
            codigo_acesso=tenant_settings.correios_codigo_acesso,
        )

        correios_token = auth_client.get_token(
            contrato=tenant_settings.correios_contrato,
            cartao=tenant_settings.correios_cartao_postagem,
        )

        if not correios_token:
            logger.error("Falha ao obter token dos Correios")
            return None

        # Salvar token cacheado
        tenant_settings.correios_token = correios_token.token
        tenant_settings.correios_token_expira = correios_token.expires_at
        tenant_settings.save(update_fields=["correios_token", "correios_token_expira"])

        token = correios_token.token

    tracking_client = CorreiosTrackingClient(token)
    auth_client = CorreiosAuthClient(
        usuario=tenant_settings.correios_usuario,
        codigo_acesso=tenant_settings.correios_codigo_acesso,
    )

    return (auth_client, tracking_client)


def process_correios_tracking(order) -> dict:
    """
    Processa o rastreio de um pedido via Correios.

    Args:
        order: Instância de Order com tracking_code

    Returns:
        Dict com resultado do processamento
    """
    from apps.orders.models import DeliveryStatus, DeliveryType
    from apps.orders.services import OrderStatusService

    result = {
        "processed": False,
        "order_code": order.code,
        "new_status": None,
        "events_count": 0,
        "message": "",
    }

    if not order.tracking_code:
        result["message"] = "Sem código de rastreio"
        return result

    if order.delivery_type not in [DeliveryType.SEDEX, DeliveryType.PAC]:
        result["message"] = "Tipo de entrega não é Correios"
        return result

    try:
        tenant_settings = order.tenant.settings
    except Exception:
        result["message"] = "Tenant sem configurações"
        return result

    # Obter cliente
    clients = get_correios_client(tenant_settings)
    if not clients:
        result["message"] = "Correios não configurado"
        return result

    _, tracking_client = clients

    # Consultar rastreio
    events = tracking_client.get_tracking(order.tracking_code)
    if events is None:
        result["message"] = "Erro ao consultar rastreio"
        return result

    result["events_count"] = len(events)

    if not events:
        result["message"] = "Nenhum evento encontrado"
        order.last_tracking_check = timezone.now()
        order.tracking_check_count += 1
        order.save(update_fields=["last_tracking_check", "tracking_check_count"])
        return result

    # Pegar evento mais recente
    latest_event = events[0]  # Já vem ordenado do mais recente

    # Atualizar campos de rastreio
    order.last_tracking_status = latest_event.status
    order.last_tracking_check = timezone.now()
    order.tracking_check_count += 1
    order.save(update_fields=["last_tracking_status", "last_tracking_check", "tracking_check_count"])

    # Mapear status
    new_delivery_status, should_notify = CorreiosStatusMapper.map_status(latest_event.status)
    result["new_status"] = new_delivery_status

    # Verificar se precisa atualizar
    current_status = order.delivery_status

    status_order = {
        DeliveryStatus.PENDING: 0,
        DeliveryStatus.SHIPPED: 1,
        DeliveryStatus.FAILED_ATTEMPT: 2,
        DeliveryStatus.DELIVERED: 3,
    }

    current_order = status_order.get(current_status, 0)
    new_order = status_order.get(new_delivery_status, 0)

    if new_order > current_order or new_delivery_status == DeliveryStatus.FAILED_ATTEMPT:
        if new_delivery_status == DeliveryStatus.SHIPPED and current_status == DeliveryStatus.PENDING:
            OrderStatusService.mark_as_shipped(order, notify=should_notify)
        elif new_delivery_status == DeliveryStatus.DELIVERED:
            OrderStatusService.mark_as_delivered(order, notify=should_notify)
        elif new_delivery_status == DeliveryStatus.FAILED_ATTEMPT:
            OrderStatusService.mark_failed_delivery(order, notify=should_notify)

    result["processed"] = True
    result["message"] = f"Último evento: {latest_event.description}"

    logger.info(
        "Rastreio Correios processado: pedido=%s, status=%s, eventos=%d",
        order.code, latest_event.status, len(events)
    )

    return result
