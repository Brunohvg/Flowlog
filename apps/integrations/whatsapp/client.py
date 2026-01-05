import logging

import requests

logger = logging.getLogger(__name__)


class EvolutionClient:
    """
    Cliente para Evolution API.
    Documentação: https://doc.evolution-api.com
    """
    
    def __init__(self, *, base_url: str, api_key: str, instance: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.instance = instance
        self.headers = {
            "apikey": self.api_key,
            "Content-Type": "application/json",
        }

    def get_instance_status(self) -> dict:
        """
        Verifica o status da instância.
        Retorna: {'connected': bool, 'number': str, 'state': str}
        """
        url = f"{self.base_url}/instance/connectionState/{self.instance}"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            # Evolution API retorna diferentes formatos dependendo da versão
            state = data.get('state') or data.get('instance', {}).get('state', '')
            connected = state.lower() in ('open', 'connected')
            
            # Tenta pegar o número conectado
            number = ''
            if connected:
                # Tenta buscar info da instância
                try:
                    info_url = f"{self.base_url}/instance/fetchInstances"
                    info_response = requests.get(info_url, headers=self.headers, timeout=10)
                    if info_response.ok:
                        instances = info_response.json()
                        for inst in instances:
                            if inst.get('name') == self.instance or inst.get('instance', {}).get('instanceName') == self.instance:
                                number = inst.get('number') or inst.get('instance', {}).get('owner', '')
                                break
                except Exception:
                    pass
            
            return {
                'connected': connected,
                'number': number,
                'state': state,
            }
            
        except requests.exceptions.RequestException as e:
            logger.error("Erro ao verificar status da instância: %s", e)
            raise

    def send_text_message(self, *, phone: str, message: str) -> dict:
        """
        Envia mensagem de texto via WhatsApp.
        """
        phone_clean = "".join(filter(str.isdigit, phone))
        
        # Adiciona código do Brasil se necessário
        if len(phone_clean) == 11:
            phone_clean = f"55{phone_clean}"
        elif len(phone_clean) == 10:
            phone_clean = f"55{phone_clean}"

        url = f"{self.base_url}/message/sendText/{self.instance}"

        payload = {
            "number": phone_clean,
            "text": message,
            "delay": 1200,  # Delay em ms para parecer mais natural
        }

        logger.info(
            "WhatsApp request | instance=%s | phone=***%s",
            self.instance,
            phone_clean[-4:],
        )

        response = requests.post(
            url,
            json=payload,
            headers=self.headers,
            timeout=10,
        )

        response.raise_for_status()

        logger.info(
            "WhatsApp success | instance=%s | phone=***%s",
            self.instance,
            phone_clean[-4:],
        )

        return response.json()
