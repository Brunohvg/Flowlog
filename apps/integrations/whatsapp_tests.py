import pytest
from django.test import override_settings

from apps.integrations.whatsapp.services import WhatsAppNotificationService


@pytest.mark.django_db
class TestWhatsAppService:
    def test_whatsapp_not_ready_if_no_instance(self, tenant):
        """Verifica se o serviço identifica que o WhatsApp não está pronto sem instância."""
        tenant.settings.whatsapp_enabled = True
        tenant.settings.evolution_instance = ""
        tenant.settings.save()

        service = WhatsAppNotificationService(tenant)
        assert service.is_ready is False

    @override_settings(EVOLUTION_API_URL="https://api.teste.com.br")
    def test_whatsapp_ready_with_config(self, tenant):
        """Verifica se o serviço identifica que o WhatsApp está pronto com instância e token."""
        tenant.settings.whatsapp_enabled = True
        tenant.settings.evolution_instance = "instancia_teste"
        tenant.settings.evolution_instance_token = "token_abc"
        tenant.settings.save()

        service = WhatsAppNotificationService(tenant)
        assert service.is_ready is True
