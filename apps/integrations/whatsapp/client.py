import logging

import requests

logger = logging.getLogger(__name__)


class EvolutionClient:
    def __init__(self, *, base_url: str, api_key: str, instance: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.instance = instance

    def send_text_message(self, *, phone: str, message: str) -> dict:
        phone_clean = "".join(filter(str.isdigit, phone))
        if len(phone_clean) == 11:
            phone_clean = f"55{phone_clean}"

        url = f"{self.base_url}/message/sendText/{self.instance}"

        payload = {
            "number": phone_clean,
            "text": message,
            "delay": 1200,
        }

        headers = {
            "apikey": self.api_key,
            "Content-Type": "application/json",
        }

        logger.info(
            "WhatsApp request | instance=%s | phone=%s",
            self.instance,
            phone_clean,
        )

        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=10,
        )

        response.raise_for_status()

        logger.info(
            "WhatsApp success | instance=%s | phone=%s",
            self.instance,
            phone_clean,
        )

        return response.json()
