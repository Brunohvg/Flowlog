"""
Cliente Evolution API - Flowlog v9.

Refatorado para produção:
- Criação automática de instância
- Obtenção de QR Code para exibição no sistema
- Verificação de status de conexão
- Tratamento robusto de erros
- Suporte a múltiplas versões da API
"""

import logging
from typing import Optional
from urllib.parse import urljoin

import requests
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)


class EvolutionAPIError(Exception):
    """Erro específico da Evolution API."""
    def __init__(self, message: str, status_code: int = None, response: dict = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class EvolutionClient:
    """
    Cliente para Evolution API.
    
    Documentação: https://doc.evolution-api.com
    
    Funcionalidades:
    - Criar/deletar instâncias automaticamente
    - Obter QR Code para conexão
    - Verificar status de conexão
    - Enviar mensagens de texto
    - Suporte a múltiplas versões da API
    """
    
    # Timeout padrão para requisições
    DEFAULT_TIMEOUT = 15
    
    def __init__(self, *, base_url: str, api_key: str, instance: str = None):
        """
        Inicializa o cliente.
        
        Args:
            base_url: URL base da Evolution API (ex: https://api.evolution.com)
            api_key: Chave de API global
            instance: Nome da instância (opcional, pode ser definido depois)
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.instance = instance
        self.headers = {
            "apikey": self.api_key,
            "Content-Type": "application/json",
        }
    
    def _request(
        self, 
        method: str, 
        endpoint: str, 
        data: dict = None, 
        timeout: int = None
    ) -> dict:
        """
        Faz requisição à API.
        
        Args:
            method: GET, POST, PUT, DELETE
            endpoint: Endpoint da API (ex: /instance/create)
            data: Dados para enviar (JSON)
            timeout: Timeout em segundos
            
        Returns:
            dict: Resposta da API
            
        Raises:
            EvolutionAPIError: Em caso de erro
        """
        url = urljoin(self.base_url, endpoint)
        timeout = timeout or self.DEFAULT_TIMEOUT
        
        try:
            response = requests.request(
                method=method,
                url=url,
                json=data,
                headers=self.headers,
                timeout=timeout,
            )
            
            # Tenta parsear JSON mesmo em erro
            try:
                result = response.json()
            except ValueError:
                result = {"raw": response.text}
            
            # Verifica erros HTTP
            if response.status_code >= 400:
                error_msg = result.get("message") or result.get("error") or str(result)
                raise EvolutionAPIError(
                    f"Erro na API: {error_msg}",
                    status_code=response.status_code,
                    response=result,
                )
            
            return result
            
        except RequestException as e:
            logger.error("Erro de conexão com Evolution API: %s", e)
            raise EvolutionAPIError(f"Erro de conexão: {str(e)}")
    
    # =========================================================================
    # GERENCIAMENTO DE INSTÂNCIA
    # =========================================================================
    
    def create_instance(self, instance_name: str, webhook_url: str = None) -> dict:
        """
        Cria uma nova instância no Evolution API.
        
        A instância é criada automaticamente e fica pronta para conexão via QR Code.
        
        Args:
            instance_name: Nome único para a instância
            webhook_url: URL para receber eventos (opcional)
            
        Returns:
            {
                "instance": {"instanceName": "...", "instanceId": "...", "status": "..."},
                "hash": "API_KEY_DA_INSTANCIA",
                "qrcode": {"base64": "...", "code": "..."} (se disponível)
            }
        """
        data = {
            "instanceName": instance_name,
            "integration": "WHATSAPP-BAILEYS",
            "qrcode": True,  # Gera QR code automaticamente
            "reject_call": True,  # Rejeita chamadas
            "always_online": True,  # Mantém online
        }
        
        if webhook_url:
            data["webhook"] = {
                "url": webhook_url,
                "byEvents": True,
                "base64": True,
                "events": [
                    "QRCODE_UPDATED",
                    "CONNECTION_UPDATE",
                    "MESSAGES_UPSERT",
                ]
            }
        
        result = self._request("POST", "/instance/create", data=data)
        
        # Atualiza instância local se criada com sucesso
        if result.get("instance", {}).get("instanceName"):
            self.instance = result["instance"]["instanceName"]
        
        # Extrai token da instância de múltiplos caminhos possíveis
        # CUIDADO: hash pode ser string ou dict dependendo da versão da API
        instance_token = None
        
        # Tenta extrair de hash (pode ser dict ou string)
        hash_value = result.get("hash")
        if isinstance(hash_value, dict):
            instance_token = hash_value.get("apikey")
        elif isinstance(hash_value, str):
            instance_token = hash_value
        
        # Outros caminhos possíveis
        if not instance_token:
            instance_token = (
                result.get("token") or
                result.get("apikey") or
                result.get("instance", {}).get("token") or
                result.get("instance", {}).get("apikey") or
                result.get("instance", {}).get("integration", {}).get("token")
            )
        
        if instance_token:
            result["token"] = instance_token
        
        logger.info("Instância criada - resultado: %s", result)
        
        return result
    
    def get_instance_token(self, instance_name: str = None) -> Optional[str]:
        """
        Busca o token de uma instância existente.
        
        Usa endpoint de fetch para obter detalhes da instância.
        
        Args:
            instance_name: Nome da instância
            
        Returns:
            Token da instância ou None se não encontrado
        """
        name = instance_name or self.instance
        if not name:
            return None
        
        try:
            # Tenta buscar instância específica
            result = self._request("GET", f"/instance/fetchInstances?instanceName={name}")
            
            # Extrai token
            if isinstance(result, list) and result:
                inst = result[0]
            elif isinstance(result, dict):
                inst = result.get("instance", result)
            else:
                return None
            
            # Extrai token com cuidado para hash string/dict
            hash_value = inst.get("hash")
            if isinstance(hash_value, dict):
                return hash_value.get("apikey")
            elif isinstance(hash_value, str):
                return hash_value
            
            return (
                inst.get("token") or
                inst.get("apikey")
            )
        except EvolutionAPIError:
            return None
    
    def delete_instance(self, instance_name: str = None) -> dict:
        """
        Deleta uma instância.
        
        Args:
            instance_name: Nome da instância (usa self.instance se não informado)
        """
        name = instance_name or self.instance
        if not name:
            raise EvolutionAPIError("Nome da instância não informado")
        
        return self._request("DELETE", f"/instance/delete/{name}")
    
    def list_instances(self) -> list:
        """
        Lista todas as instâncias disponíveis.
        
        Returns:
            Lista de instâncias com seus status
        """
        result = self._request("GET", "/instance/fetchInstances")
        
        # Normaliza resposta (pode variar entre versões)
        if isinstance(result, list):
            return result
        return result.get("instances", result.get("data", []))
    
    def instance_exists(self, instance_name: str = None) -> bool:
        """
        Verifica se uma instância existe.
        """
        name = instance_name or self.instance
        if not name:
            return False
        
        try:
            instances = self.list_instances()
            for inst in instances:
                inst_name = inst.get("name") or inst.get("instance", {}).get("instanceName")
                if inst_name == name:
                    return True
            return False
        except EvolutionAPIError:
            return False
    
    # =========================================================================
    # CONEXÃO / QR CODE
    # =========================================================================
    
    def get_connection_state(self, instance_name: str = None) -> dict:
        """
        Obtém o estado de conexão da instância.
        
        Returns:
            {
                "connected": bool,
                "state": "open" | "close" | "connecting",
                "number": str (número conectado, se disponível)
            }
        """
        name = instance_name or self.instance
        if not name:
            raise EvolutionAPIError("Nome da instância não informado")
        
        result = self._request("GET", f"/instance/connectionState/{name}")
        
        # Normaliza resposta (varia entre versões)
        state = (
            result.get("state") or 
            result.get("instance", {}).get("state") or 
            "close"
        )
        
        connected = state.lower() in ("open", "connected")
        
        # Tenta obter número conectado
        number = ""
        if connected:
            number = (
                result.get("number") or
                result.get("instance", {}).get("owner") or
                ""
            )
        
        return {
            "connected": connected,
            "state": state,
            "number": number,
        }
    
    def get_qrcode(self, instance_name: str = None) -> dict:
        """
        Obtém o QR Code para conexão.
        
        IMPORTANTE: Tenta extrair QR de múltiplos caminhos possíveis,
        pois diferentes versões da Evolution API retornam em formatos diferentes.
        
        Returns:
            {
                "qrcode": str (base64 da imagem ou código texto),
                "code": str (código para gerar QR manualmente),
                "pairingCode": str (código de pareamento numérico, se disponível)
            }
        """
        name = instance_name or self.instance
        if not name:
            raise EvolutionAPIError("Nome da instância não informado")
        
        result = self._request("GET", f"/instance/connect/{name}")
        
        # Extrai QR Code de múltiplos caminhos possíveis
        qrcode = None
        code = None
        pairing_code = None
        
        # Formato v1: { "base64": "...", "code": "..." }
        if result.get("base64"):
            qrcode = result["base64"]
            code = result.get("code")
        
        # Formato v2: { "qrcode": { "base64": "...", "code": "..." } }
        elif result.get("qrcode"):
            qr_data = result["qrcode"]
            if isinstance(qr_data, dict):
                qrcode = qr_data.get("base64")
                code = qr_data.get("code")
            else:
                qrcode = qr_data
        
        # Formato v3: { "instance": { "qrcode": "..." } }
        elif result.get("instance", {}).get("qrcode"):
            qrcode = result["instance"]["qrcode"]
        
        # Código de pareamento (para vincular sem QR)
        pairing_code = result.get("pairingCode") or result.get("code")
        
        if not qrcode and not pairing_code:
            # Verifica se já está conectado
            state = self.get_connection_state(name)
            if state["connected"]:
                raise EvolutionAPIError(
                    "Instância já está conectada. Não é necessário QR Code.",
                    response={"connected": True, "number": state["number"]}
                )
            raise EvolutionAPIError("QR Code não disponível", response=result)
        
        return {
            "qrcode": qrcode,
            "code": code,
            "pairingCode": pairing_code,
        }
    
    def restart_instance(self, instance_name: str = None) -> dict:
        """Reinicia a instância."""
        name = instance_name or self.instance
        if not name:
            raise EvolutionAPIError("Nome da instância não informado")
        
        return self._request("PUT", f"/instance/restart/{name}")
    
    def logout_instance(self, instance_name: str = None) -> dict:
        """Desconecta o WhatsApp (logout) mantendo a instância."""
        name = instance_name or self.instance
        if not name:
            raise EvolutionAPIError("Nome da instância não informado")
        
        return self._request("DELETE", f"/instance/logout/{name}")
    
    # =========================================================================
    # ENVIO DE MENSAGENS
    # =========================================================================
    
    def send_text_message(self, *, phone: str, message: str) -> dict:
        """
        Envia mensagem de texto via WhatsApp.
        
        Args:
            phone: Número do destinatário (com ou sem código de país)
            message: Texto da mensagem
            
        Returns:
            Resposta da API com status do envio
        """
        if not self.instance:
            raise EvolutionAPIError("Instância não configurada")
        
        # Normaliza telefone
        phone_clean = "".join(filter(str.isdigit, phone))
        
        # Adiciona código do Brasil se necessário
        if len(phone_clean) == 11:  # DDD + número (11 dígitos)
            phone_clean = f"55{phone_clean}"
        elif len(phone_clean) == 10:  # DDD + número sem 9 (10 dígitos)
            phone_clean = f"55{phone_clean}"
        elif len(phone_clean) == 9:  # Só número sem DDD
            raise EvolutionAPIError("Telefone inválido: informe com DDD")
        
        payload = {
            "number": phone_clean,
            "text": message,
            "delay": 1200,  # Delay em ms para parecer mais natural
        }
        
        logger.info(
            "WhatsApp: enviando mensagem | instance=%s | phone=***%s",
            self.instance,
            phone_clean[-4:],
        )
        
        result = self._request(
            "POST", 
            f"/message/sendText/{self.instance}", 
            data=payload
        )
        
        logger.info(
            "WhatsApp: mensagem enviada | instance=%s | phone=***%s",
            self.instance,
            phone_clean[-4:],
        )
        
        return result
    
    # =========================================================================
    # UTILITÁRIOS
    # =========================================================================
    
    def test_connection(self) -> dict:
        """
        Testa a conexão com a API.
        
        Returns:
            {
                "api_ok": bool,
                "instance_exists": bool,
                "connected": bool,
                "number": str
            }
        """
        result = {
            "api_ok": False,
            "instance_exists": False,
            "connected": False,
            "number": "",
            "error": None,
        }
        
        try:
            # Testa se API está acessível
            instances = self.list_instances()
            result["api_ok"] = True
            
            if self.instance:
                # Verifica se instância existe
                result["instance_exists"] = self.instance_exists()
                
                if result["instance_exists"]:
                    # Verifica status de conexão
                    state = self.get_connection_state()
                    result["connected"] = state["connected"]
                    result["number"] = state["number"]
                    
        except EvolutionAPIError as e:
            result["error"] = str(e)
        
        return result
    
    def ensure_instance(self, instance_name: str, webhook_url: str = None) -> dict:
        """
        Garante que uma instância existe, criando se necessário.
        
        Args:
            instance_name: Nome da instância
            webhook_url: URL de webhook (opcional)
            
        Returns:
            {
                "created": bool (True se foi criada, False se já existia),
                "instance": {...},
                "qrcode": {...} (se criada e não conectada)
            }
        """
        self.instance = instance_name
        
        # Verifica se já existe
        if self.instance_exists():
            state = self.get_connection_state()
            
            result = {
                "created": False,
                "instance": {"instanceName": instance_name},
                "connected": state["connected"],
                "number": state["number"],
            }
            
            # Se não está conectada, retorna QR
            if not state["connected"]:
                try:
                    qr = self.get_qrcode()
                    result["qrcode"] = qr
                except EvolutionAPIError:
                    pass
            
            return result
        
        # Cria nova instância
        create_result = self.create_instance(instance_name, webhook_url)
        
        return {
            "created": True,
            "instance": create_result.get("instance", {}),
            "hash": create_result.get("hash"),
            "qrcode": create_result.get("qrcode"),
            "connected": False,
        }
