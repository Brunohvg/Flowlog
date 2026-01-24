from unittest.mock import patch

import pytest

from apps.payments.services import PagarmeError, create_payment_link_for_order


@pytest.mark.django_db
class TestPaymentIntegration:

    @patch("apps.payments.services.PagarmeService.create_payment_link")
    def test_create_payment_link_success(self, mock_pagarme, tenant, user, customer, db):
        """Testa a criação de um link de pagamento vinculado a um pedido."""
        from apps.orders.models import Order

        # Configura tenant settings
        tenant.settings.pagarme_api_key = "sk_test_123"
        tenant.settings.save()

        order = Order.objects.create(
            tenant=tenant,
            customer=customer,
            seller=user,
            total_value=250.00,
            delivery_address="Teste"
        )

        # Mock da resposta do Pagar.me
        mock_pagarme.return_value = {
            "id": "li_XXXXX",
            "url": "https://pagar.me/checkout/XXXX",
            "status": "active",
            "expires_at": None,
            "raw_response": {}
        }

        payment_link = create_payment_link_for_order(order, installments=3, created_by=user)

        assert payment_link.checkout_url == "https://pagar.me/checkout/XXXX"
        assert payment_link.amount == 250.00
        assert payment_link.tenant == tenant
        assert payment_link.order == order

    def test_create_payment_link_missing_config(self, tenant, user, customer):
        """Testa falha ao criar link sem configuração do Pagar.me."""
        from apps.orders.models import Order

        # Garante que não tem chave
        tenant.settings.pagarme_api_key = ""
        tenant.settings.save()

        order = Order.objects.create(
            tenant=tenant,
            customer=customer,
            seller=user,
            total_value=10.00,
            delivery_address="Teste"
        )

        with pytest.raises(PagarmeError, match="Pagar.me não configurado"):
            create_payment_link_for_order(order)
