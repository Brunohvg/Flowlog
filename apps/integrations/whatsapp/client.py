"""
Cliente Evolution API - Flowlog.

Funcionalidades:
- Criação automática de instância
- Obtenção de QR Code para exibição no sistema
- Verificação de status de conexão
- Tratamento robusto de erros
- Suporte a múltiplas versões da API
- Logging estruturado com correlation_id
- Medição de tempo de resposta
"""

import logging
import time
import uuid
from typing import Optional
from urllib.parse import urljoin

import requests
from requests.exceptions import RequestException, Timeout, ConnectionError

logger = logging.getLogger("flowlog.whatsapp.client")


class EvolutionAPIError(Exception):
    """
    Erro específico da Evolution API.
    
    Attributes:
        message: Mensagem de erro
        status_code: Código HTTP (se aplicável)
        response: Resposta da API (se aplicável)
        request_data: Dados enviados na requisição
    """
    def __init__(
        self, 
        message: str, 
        status_code: int = None, 
        response: dict = None,
        request_data: dict = None
    ):
        super().__init__(message)
        self.status_code = status_code
        self.response = response
        self.request_data = request_data


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
    - Logging estruturado para diagnóstico
    """
    
    # Timeout padrão para requisições
    DEFAULT_TIMEOUT = 15
    
    def __init__(
        self, 
        *, 
        base_url: str, 
        api_key: str, 
        instance: str = None,
        correlation_id: str = None
    ):
        """
        Inicializa o cliente.
        
        Args:
            base_url: URL base da Evolution API (ex: https://api.evolution.com)
            api_key: Chave de API global
            instance: Nome da instância (opcional, pode ser definido depois)
            correlation_id: ID de correlação para rastreamento
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.instance = instance
        self.correlation_id = correlation_id or str(uuid.uuid4())[:8]
        self.headers = {
            "apikey": self.api_key,
            "Content-Type": "application/json",
        }
    
    def _mask_sensitive_data(self, data: dict) -> dict:
        """Mascara dados sensíveis para logging."""
        if not data:
            return data
        
        masked = dict(data)
        sensitive_keys = ['apikey', 'token', 'password', 'secret']
        
        for key in sensitive_keys:
            if key in masked:
                masked[key] = "***MASKED***"
        
        # Mascara números de telefone
        if 'number' in masked and isinstance(masked['number'], str):
            phone = masked['number']
            if len(phone) >= 4:
                masked['number'] = f"***{phone[-4:]}"
        
        return masked
    
    def _log_to_db(
        self, 
        method: str, 
        endpoint: str, 
        request_data: dict,
        response_data: dict,
        status_code: int,
        response_time_ms: int,
        error_message: str = None
    ):
        """
        Registra requisição no banco de dados.
        
        Args:
            method: Método HTTP
            endpoint: Endpoint da API
            request_data: Dados enviados
            response_data: Dados recebidos
            status_code: Código de status HTTP
            response_time_ms: Tempo de resposta em ms
            error_message: Mensagem de erro (se houver)
        """
        try:
            from django.apps import apps
            APIRequestLog = apps.get_model("integrations", "APIRequestLog")
            
            APIRequestLog.objects.create(
                correlation_id=self.correlation_id,
                method=method,
                endpoint=endpoint,
                instance_name=self.instance,
                request_body=request_data,
                response_body=response_data,
                status_code=status_code,
                response_time_ms=response_time_ms,
                error_message=error_message,
            )
            
        except LookupError:
            # Model não existe ainda
            pass
        except Exception as e:
            logger.warning(
                "API_LOG_DB_ERROR | correlation_id=%s | error=%s",
                self.correlation_id, str(e)
            )
    
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
        
        # Dados mascarados para log
        masked_data = self._mask_sensitive_data(data)
        
        logger.debug(
            "API_REQUEST_START | correlation_id=%s | method=%s | "
            "endpoint=%s | instance=%s",
            self.correlation_id, method, endpoint, self.instance
        )
        
        start_time = time.time()
        status_code = None
        result = None
        error_message = None
        
        try:
            response = requests.request(
                method=method,
                url=url,
                json=data,
                headers=self.headers,
                timeout=timeout,
            )
            
            response_time_ms = int((time.time() - start_time) * 1000)
            status_code = response.status_code
            
            # Tenta parsear JSON mesmo em erro
            try:
                result = response.json()
            except ValueError:
                result = {"raw": response.text}
            
            # Log no banco
            self._log_to_db(
                method=method,
                endpoint=endpoint,
                request_data=masked_data,
                response_data=result,
                status_code=status_code,
                response_time_ms=response_time_ms,
            )
            
            # Verifica erros HTTP
            if response.status_code >= 400:
                error_msg = result.get("message") or result.get("error") or str(result)
                error_message = f"HTTP {status_code}: {error_msg}"
                
                logger.error(
                    "API_RESPONSE_ERROR | correlation_id=%s | method=%s | "
                    "endpoint=%s | status_code=%d | response_time_ms=%d | error=%s",
                    self.correlation_id, method, endpoint, 
                    status_code, response_time_ms, error_msg
                )
                
                raise EvolutionAPIError(
                    f"Erro na API: {error_msg}",
                    status_code=response.status_code,
                    response=result,
                    request_data=masked_data,
                )
            
            logger.info(
                "API_RESPONSE_SUCCESS | correlation_id=%s | method=%s | "
                "endpoint=%s | status_code=%d | response_time_ms=%d",
                self.correlation_id, method, endpoint, 
                status_code, response_time_ms
            )
            
            return result
            
        except Timeout as e:
            response_time_ms = int((time.time() - start_time) * 1000)
            error_message = f"Timeout após {timeout}s"
            
            self._log_to_db(
                method=method,
                endpoint=endpoint,
                request_data=masked_data,
                response_data=None,
                status_code=0,
                response_time_ms=response_time_ms,
                error_message=error_message,
            )
            
            logger.error(
                "API_TIMEOUT | correlation_id=%s | method=%s | "
                "endpoint=%s | timeout=%ds | response_time_ms=%d",
                self.correlation_id, method, endpoint, 
                timeout, response_time_ms
            )
            
            raise EvolutionAPIError(
                f"Timeout: API não respondeu em {timeout}s",
                request_data=masked_data,
            )
            
        except ConnectionError as e:
            response_time_ms = int((time.time() - start_time) * 1000)
            error_message = f"Erro de conexão: {str(e)}"
            
            self._log_to_db(
                method=method,
                endpoint=endpoint,
                request_data=masked_data,
                response_data=None,
                status_code=0,
                response_time_ms=response_time_ms,
                error_message=error_message,
            )
            
            logger.error(
                "API_CONNECTION_ERROR | correlation_id=%s | method=%s | "
                "endpoint=%s | error=%s",
                self.correlation_id, method, endpoint, str(e)
            )
            
            raise EvolutionAPIError(
                f"Erro de conexão: {str(e)}",
                request_data=masked_data,
            )
            
        except RequestException as e:
            response_time_ms = int((time.time() - start_time) * 1000)
            error_message = str(e)
            
            self._log_to_db(
                method=method,
                endpoint=endpoint,
                request_data=masked_data,
                response_data=None,
                status_code=0,
                response_time_ms=response_time_ms,
                error_message=error_message,
            )
            
            logger.error(
                "API_REQUEST_ERROR | correlation_id=%s | method=%s | "
                "endpoint=%s | error_type=%s | error=%s",
                self.correlation_id, method, endpoint, 
                type(e).__name__, str(e)
            )
            
            raise EvolutionAPIError(
                f"Erro de requisição: {str(e)}",
                request_data=masked_data,
            )
    
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
        logger.info(
            "INSTANCE_CREATE_START | correlation_id=%s | instance=%s",
            self.correlation_id, instance_name
        )
        
        data = {
            "instanceName": instance_name,
            "integration": "WHATSAPP-BAILEYS",
            "qrcode": True,
            "reject_call": True,
            "always_online": True,
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
        instance_token = None
        
        hash_value = result.get("hash")
        if isinstance(hash_value, dict):
            instance_token = hash_value.get("apikey")
        elif isinstance(hash_value, str):
            instance_token = hash_value
        
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
        
        logger.info(
            "INSTANCE_CREATE_SUCCESS | correlation_id=%s | instance=%s | "
            "has_token=%s",
            self.correlation_id, instance_name, instance_token is not None
        )
        
        return result
    
    def get_instance_token(self, instance_name: str = None) -> Optional[str]:
        """
        Busca o token de uma instância existente.
        """
        name = instance_name or self.instance
        if not name:
            return None
        
        try:
            result = self._request("GET", f"/instance/fetchInstances?instanceName={name}")
            
            if isinstance(result, list) and result:
                inst = result[0]
            elif isinstance(result, dict):
                inst = result.get("instance", result)
            else:
                return None
            
            hash_value = inst.get("hash")
            if isinstance(hash_value, dict):
                return hash_value.get("apikey")
            elif isinstance(hash_value, str):
                return hash_value
            
            return inst.get("token") or inst.get("apikey")
            
        except EvolutionAPIError:
            return None
    
    def delete_instance(self, instance_name: str = None) -> dict:
        """Deleta uma instância."""
        name = instance_name or self.instance
        if not name:
            raise EvolutionAPIError("Nome da instância não informado")
        
        logger.info(
            "INSTANCE_DELETE | correlation_id=%s | instance=%s",
            self.correlation_id, name
        )
        
        return self._request("DELETE", f"/instance/delete/{name}")
    
    def list_instances(self) -> list:
        """Lista todas as instâncias."""
        result = self._request("GET", "/instance/fetchInstances")
        return result if isinstance(result, list) else []
    
    def instance_exists(self, instance_name: str = None) -> bool:
        """Verifica se uma instância existe."""
        name = instance_name or self.instance
        if not name:
            return False
        
        try:
            instances = self.list_instances()
            for inst in instances:
                inst_name = inst.get("instanceName") or inst.get("instance", {}).get("instanceName")
                if inst_name == name:
                    return True
            return False
        except EvolutionAPIError:
            return False
    
    # =========================================================================
    # CONEXÃO E QR CODE
    # =========================================================================
    
    def get_connection_state(self, instance_name: str = None) -> dict:
        """
        Verifica o estado de conexão do WhatsApp.
        
        Returns:
            {"connected": bool, "state": str, "number": str}
        """
        name = instance_name or self.instance
        if not name:
            raise EvolutionAPIError("Nome da instância não informado")
        
        result = self._request("GET", f"/instance/connectionState/{name}")
        
        # Normaliza resposta
        state = (
            result.get("state") or
            result.get("instance", {}).get("state") or
            "unknown"
        )
        
        connected = state.lower() in ["open", "connected", "online"]
        
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
        
        pairing_code = result.get("pairingCode") or result.get("code")
        
        if not qrcode and not pairing_code:
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
        
        logger.info(
            "INSTANCE_RESTART | correlation_id=%s | instance=%s",
            self.correlation_id, name
        )
        
        return self._request("PUT", f"/instance/restart/{name}")
    
    def logout_instance(self, instance_name: str = None) -> dict:
        """Desconecta o WhatsApp (logout) mantendo a instância."""
        name = instance_name or self.instance
        if not name:
            raise EvolutionAPIError("Nome da instância não informado")
        
        logger.info(
            "INSTANCE_LOGOUT | correlation_id=%s | instance=%s",
            self.correlation_id, name
        )
        
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
            "delay": 1200,
        }
        
        # Log com telefone mascarado
        phone_masked = f"***{phone_clean[-4:]}" if len(phone_clean) >= 4 else "***"
        
        logger.info(
            "SEND_MESSAGE_START | correlation_id=%s | instance=%s | phone=%s",
            self.correlation_id, self.instance, phone_masked
        )
        
        result = self._request(
            "POST", 
            f"/message/sendText/{self.instance}", 
            data=payload
        )
        
        logger.info(
            "SEND_MESSAGE_SUCCESS | correlation_id=%s | instance=%s | phone=%s",
            self.correlation_id, self.instance, phone_masked
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
                "number": str,
                "error": str
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
            instances = self.list_instances()
            result["api_ok"] = True
            
            if self.instance:
                result["instance_exists"] = self.instance_exists()
                
                if result["instance_exists"]:
                    state = self.get_connection_state()
                    result["connected"] = state["connected"]
                    result["number"] = state["number"]
                    
        except EvolutionAPIError as e:
            result["error"] = str(e)
        
        return result
    
    def ensure_instance(self, instance_name: str, webhook_url: str = None) -> dict:
        """
        Garante que uma instância existe, criando se necessário.
        """
        self.instance = instance_name
        
        if self.instance_exists():
            state = self.get_connection_state()
            
            result = {
                "created": False,
                "instance": {"instanceName": instance_name},
                "connected": state["connected"],
                "number": state["number"],
            }
            
            if not state["connected"]:
                try:
                    qr = self.get_qrcode()
                    result["qrcode"] = qr
                except EvolutionAPIError:
                    pass
            
            return result
        
        create_result = self.create_instance(instance_name, webhook_url)
        
        return {
            "created": True,
            "instance": create_result.get("instance", {}),
            "hash": create_result.get("hash"),
            "qrcode": create_result.get("qrcode"),
            "connected": False,
        }
