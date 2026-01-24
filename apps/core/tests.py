import pytest
from django.core.exceptions import ValidationError

from apps.orders.models import Order


@pytest.mark.django_db
class TestTenantIsolation:
    def test_tenant_manager_filtering(self, tenant, tenant2, user, customer):
        """Verifica se o TenantManager filtra corretamente por tenant."""
        # Criamos um pedido para cada tenant
        Order.objects.create(
            tenant=tenant,
            customer=customer,
            seller=user,
            total_value=100.00,
            delivery_address="Rua A, 1"
        )

        # Simulamos outro customer no tenant2
        from apps.orders.models import Customer
        customer2 = Customer.objects.create(
            tenant=tenant2,
            name="Cliente 2",
            phone="11888888888",
            phone_normalized="11888888888"
        )
        # Simulamos um user no tenant2
        from apps.accounts.models import User
        user2 = User.objects.create_user(
            email="vendedor_iso@teste.com.br",
            password="password123",
            tenant=tenant2
        )

        Order.objects.create(
            tenant=tenant2,
            customer=customer2,
            seller=user2,
            total_value=200.00,
            delivery_address="Rua B, 2"
        )

        # O total de pedidos no banco é 2
        assert Order.objects.count() == 2

        # Filtramos pelo manager customizado
        assert Order.objects.for_tenant(tenant).count() == 1
        assert Order.objects.for_tenant(tenant2).count() == 1

    def test_prevent_tenant_change(self, tenant, tenant2, user, customer):
        """Verifica se o TenantModel impede a troca de tenant em um update."""
        order = Order.objects.create(
            tenant=tenant,
            customer=customer,
            seller=user,
            total_value=100.00,
            delivery_address="Rua X, 10"
        )

        order.tenant = tenant2

        # O save deve lançar ValidationError se o check estiver ativo
        with pytest.raises(ValidationError, match="Não é permitido alterar o tenant."):
            order.save(check_tenant=True)

@pytest.mark.django_db
class TestViewIsolation:
    def test_dashboard_kpi_isolation(self, client, tenant, tenant2, user, customer):
        """Verifica se o Dashboard mostra apenas KPIs do tenant logado."""
        from django.urls import reverse

        from apps.accounts.models import User
        from apps.orders.models import Order

        # Pedido no tenant do usuário (Pago)
        Order.objects.create(
            tenant=tenant, customer=customer, seller=user,
            total_value=500.00, payment_status="paid",
            delivery_address="Teste"
        )

        # Usuário e Pedido em OUTRO tenant (Pago)
        user2 = User.objects.create_user(
            email="vendedor_view@outro.com.br",
            password="password123",
            tenant=tenant2
        )
        Order.objects.create(
            tenant=tenant2,
            customer=customer,
            seller=user2,
            total_value=1000.00, payment_status="paid",
            delivery_address="Teste"
        )

        client.force_login(user)
        response = client.get(reverse("dashboard"))

        assert response.status_code == 200
        # O revenue no contexto deve ser 500, não 1500
        assert float(response.context["stats"]["revenue"]) == 500.0
