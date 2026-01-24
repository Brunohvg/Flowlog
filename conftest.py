import pytest

from apps.accounts.models import User
from apps.orders.models import Customer
from apps.tenants.models import Tenant


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(
        name="Loja de Teste",
        slug="loja-de-teste",
        contact_email="teste@flowlog.com.br"
    )

@pytest.fixture
def tenant2(db):
    return Tenant.objects.create(
        name="Outra Loja",
        slug="outra-loja",
        contact_email="outra@flowlog.com.br"
    )

@pytest.fixture
def user(db, tenant):
    return User.objects.create_user(
        email="vendedor@teste.com.br",
        password="password123",
        tenant=tenant,
        first_name="Vendedor",
        last_name="Teste"
    )

@pytest.fixture
def customer(db, tenant):
    return Customer.objects.create(
        tenant=tenant,
        name="Cliente João",
        phone="11999999999",
        phone_normalized="11999999999"
    )
