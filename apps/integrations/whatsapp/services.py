import logging

from django.conf import settings

from apps.integrations.whatsapp.client import EvolutionClient

logger = logging.getLogger(__name__)


class WhatsAppNotificationService:
    def __init__(self, tenant):
        self.tenant = tenant
        self.tenant_settings = tenant.settings

        self.client = EvolutionClient(
            base_url=settings.EVOLUTION_API_URL,
            api_key=settings.EVOLUTION_API_KEY,
            instance=settings.EVOLUTION_INSTANCE,
        )

    def send_order_created(self, order):
        if not self._is_enabled():
            logger.info(
                "WhatsApp disabled | tenant=%s | order=%s",
                self.tenant.id,
                order.id,
            )
            return

        logger.info(
            "Send WhatsApp | event=order_created | tenant=%s | order=%s",
            self.tenant.id,
            order.id,
        )

        message = self.tenant_settings.msg_order_created.format(
            nome=order.customer.name,
            codigo=order.code,
            valor=order.total_value,
        )

        self.client.send_text_message(
            phone=order.customer.phone,
            message=message,
        )

    def _is_enabled(self) -> bool:
        return bool(self.tenant_settings.whatsapp_enabled)
