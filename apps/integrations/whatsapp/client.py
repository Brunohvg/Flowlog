"""
Evolution API Client - Flowlog.
Com logging de requisições para diagnóstico.
"""

import time
import logging
import uuid
from urllib.parse import urljoin
import requests
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)


class EvolutionAPIError(Exception):
    def __init__(self, message: str, status_code: int = None, response: dict = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


def _log_api_request(*, correlation_id: str, method: str, endpoint: str, instance_name: str = None,
                     request_body: dict = None, status_code: int = 0, response_body: dict = None,
                     response_time_ms: int = 0, error_message: str = ""):
    """
    Salva log de requisição API de forma segura.
    Nunca falha - apenas loga warning se der erro.
    """
    try:
        from apps.integrations.models import APIRequestLog
        
        # Limpa dados sensíveis do request
        safe_request = None
        if request_body:
            safe_request = {k: v for k, v in request_body.items() if k not in ['apikey', 'token', 'password']}
        
        APIRequestLog.objects.create(
            correlation_id=correlation_id,
            method=method,
            endpoint=endpoint[:500],  # Limita tamanho
            instance_name=instance_name,
            request_body=safe_request,
            status_code=status_code,
            response_body=response_body,
            response_time_ms=response_time_ms,
            error_message=error_message[:1000] if error_message else "",
        )
    except Exception as e:
        logger.warning("[APIRequestLog] Falha ao salvar log: %s", e)


class EvolutionClient:
    DEFAULT_TIMEOUT = 15
    
    def __init__(self, *, base_url: str, api_key: str, instance: str = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.instance = instance
        self.headers = {"apikey": self.api_key, "Content-Type": "application/json"}
    
    def _request(self, method: str, endpoint: str, data: dict = None, timeout: int = None) -> dict:
        url = urljoin(self.base_url, endpoint)
        timeout = timeout or self.DEFAULT_TIMEOUT
        correlation_id = str(uuid.uuid4())[:12]
        start_time = time.time()
        
        try:
            response = requests.request(method=method, url=url, json=data, headers=self.headers, timeout=timeout)
            response_time_ms = int((time.time() - start_time) * 1000)
            
            try:
                result = response.json()
            except ValueError:
                result = {"raw": response.text}
            
            # Log da requisição (sucesso ou erro da API)
            _log_api_request(
                correlation_id=correlation_id,
                method=method,
                endpoint=endpoint,
                instance_name=self.instance,
                request_body=data,
                status_code=response.status_code,
                response_body=result if response.status_code < 400 else None,
                response_time_ms=response_time_ms,
                error_message=str(result) if response.status_code >= 400 else "",
            )
            
            if response.status_code >= 400:
                raise EvolutionAPIError(f"API Error: {result.get('message', result)}", response.status_code, result)
            return result
            
        except RequestException as e:
            response_time_ms = int((time.time() - start_time) * 1000)
            
            # Log do erro de conexão
            _log_api_request(
                correlation_id=correlation_id,
                method=method,
                endpoint=endpoint,
                instance_name=self.instance,
                request_body=data,
                status_code=0,
                response_time_ms=response_time_ms,
                error_message=f"Connection error: {str(e)}",
            )
            
            raise EvolutionAPIError(f"Connection error: {str(e)}")
    
    def create_instance(self, instance_name: str, webhook_url: str = None) -> dict:
        data = {
            "instanceName": instance_name,
            "integration": "WHATSAPP-BAILEYS",
            "qrcode": True,
            "reject_call": True,
            "always_online": True,
        }
        if webhook_url:
            data["webhook"] = {"url": webhook_url, "byEvents": True, "base64": True,
                              "events": ["QRCODE_UPDATED", "CONNECTION_UPDATE", "MESSAGES_UPSERT"]}
        result = self._request("POST", "/instance/create", data=data)
        if result.get("instance", {}).get("instanceName"):
            self.instance = result["instance"]["instanceName"]
        hash_value = result.get("hash")
        token = hash_value.get("apikey") if isinstance(hash_value, dict) else hash_value if isinstance(hash_value, str) else None
        if not token:
            token = result.get("token") or result.get("apikey") or result.get("instance", {}).get("token")
        if token:
            result["token"] = token
        return result
    
    def get_instance_token(self, instance_name: str = None):
        name = instance_name or self.instance
        if not name:
            return None
        try:
            result = self._request("GET", f"/instance/fetchInstances?instanceName={name}")
            inst = result[0] if isinstance(result, list) and result else result.get("instance", result) if isinstance(result, dict) else None
            if not inst:
                return None
            hash_value = inst.get("hash")
            return hash_value.get("apikey") if isinstance(hash_value, dict) else hash_value if isinstance(hash_value, str) else inst.get("token") or inst.get("apikey")
        except EvolutionAPIError:
            return None
    
    def delete_instance(self, instance_name: str = None) -> dict:
        name = instance_name or self.instance
        if not name:
            raise EvolutionAPIError("Instance name required")
        return self._request("DELETE", f"/instance/delete/{name}")
    
    def list_instances(self) -> list:
        result = self._request("GET", "/instance/fetchInstances")
        return result if isinstance(result, list) else result.get("instances", [])
    
    def instance_exists(self, instance_name: str = None) -> bool:
        name = instance_name or self.instance
        if not name:
            return False
        try:
            instances = self.list_instances()
            return any(i.get("instance", {}).get("instanceName") == name or i.get("instanceName") == name for i in instances)
        except EvolutionAPIError:
            return False
    
    def get_connection_state(self, instance_name: str = None) -> dict:
        name = instance_name or self.instance
        if not name:
            raise EvolutionAPIError("Instance name required")
        result = self._request("GET", f"/instance/connectionState/{name}")
        state = result.get("state") or result.get("instance", {}).get("state") or "unknown"
        connected = state.lower() in ["open", "connected"]
        number = result.get("number") or result.get("instance", {}).get("owner") or "" if connected else ""
        return {"connected": connected, "state": state, "number": number}
    
    def get_qrcode(self, instance_name: str = None) -> dict:
        name = instance_name or self.instance
        if not name:
            raise EvolutionAPIError("Instance name required")
        result = self._request("GET", f"/instance/connect/{name}")
        qrcode = code = pairing = None
        if result.get("base64"):
            qrcode, code = result["base64"], result.get("code")
        elif result.get("qrcode"):
            qr = result["qrcode"]
            qrcode, code = (qr.get("base64"), qr.get("code")) if isinstance(qr, dict) else (qr, None)
        elif result.get("instance", {}).get("qrcode"):
            qrcode = result["instance"]["qrcode"]
        pairing = result.get("pairingCode") or result.get("code")
        if not qrcode and not pairing:
            state = self.get_connection_state(name)
            if state["connected"]:
                raise EvolutionAPIError("Already connected", response={"connected": True, "number": state["number"]})
            raise EvolutionAPIError("QR Code unavailable", response=result)
        return {"qrcode": qrcode, "code": code, "pairingCode": pairing}
    
    def restart_instance(self, instance_name: str = None) -> dict:
        name = instance_name or self.instance
        if not name:
            raise EvolutionAPIError("Instance name required")
        return self._request("PUT", f"/instance/restart/{name}")
    
    def logout_instance(self, instance_name: str = None) -> dict:
        name = instance_name or self.instance
        if not name:
            raise EvolutionAPIError("Instance name required")
        return self._request("DELETE", f"/instance/logout/{name}")
    
    def send_text_message(self, *, phone: str, message: str) -> dict:
        if not self.instance:
            raise EvolutionAPIError("Instance not configured")
        phone_clean = "".join(filter(str.isdigit, phone))
        if len(phone_clean) in [10, 11]:
            phone_clean = f"55{phone_clean}"
        elif len(phone_clean) == 9:
            raise EvolutionAPIError("Invalid phone: include area code")
        payload = {"number": phone_clean, "text": message, "delay": 1200}
        return self._request("POST", f"/message/sendText/{self.instance}", data=payload)
    
    def test_connection(self) -> dict:
        result = {"api_ok": False, "instance_exists": False, "connected": False, "number": "", "error": None}
        try:
            self.list_instances()
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
        self.instance = instance_name
        if self.instance_exists():
            state = self.get_connection_state()
            result = {"created": False, "instance": {"instanceName": instance_name}, "connected": state["connected"], "number": state["number"]}
            if not state["connected"]:
                try:
                    result["qrcode"] = self.get_qrcode()
                except EvolutionAPIError:
                    pass
            return result
        create_result = self.create_instance(instance_name, webhook_url)
        return {"created": True, "instance": create_result.get("instance", {}), "hash": create_result.get("hash"),
                "qrcode": create_result.get("qrcode"), "connected": False}
