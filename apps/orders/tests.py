from unittest.mock import patch

import pytest

from apps.orders.models import DeliveryStatus, Order, OrderStatus, PaymentStatus
from apps.orders.services import OrderService, OrderStatusService


@pytest.mark.django_db
class TestOrderStatusWorkflow:

    @patch("apps.orders.services._send_whatsapp_with_snapshot")
    def test_complete_order_lifecycle(self, mock_whatsapp, tenant, user, customer):
        """Testa o ciclo completo de um pedido: Criar -> Pagar -> Enviar -> Entregar."""

        # 1. Criar pedido
        order_data = {
            "customer_name": customer.name,
            "customer_phone": customer.phone,
            "total_value": 150.50,
            "delivery_type": "motoboy",
            "delivery_address": "Rua Teste, 123",
            "is_priority": False
        }

        order = OrderService().create_order(
            tenant=tenant,
            seller=user,
            data=order_data
        )

        assert order.order_status == OrderStatus.PENDING
        assert order.payment_status == PaymentStatus.PENDING
        assert mock_whatsapp.called
        mock_whatsapp.reset_mock()

        # 2. Marcar como pago
        OrderStatusService().mark_as_paid(order=order, actor=user)
        order.refresh_from_db()
        assert order.payment_status == PaymentStatus.PAID
        assert order.order_status == OrderStatus.CONFIRMED
        assert mock_whatsapp.called
        mock_whatsapp.reset_mock()

        # 3. Marcar como enviado
        OrderStatusService().mark_as_shipped(order=order, actor=user, tracking_code="TEST123UI")
        order.refresh_from_db()
        assert order.delivery_status == DeliveryStatus.SHIPPED
        assert order.tracking_code == "TEST123UI"
        assert mock_whatsapp.called
        mock_whatsapp.reset_mock()

        # 4. Marcar como entregue
        OrderStatusService().mark_as_delivered(order=order, actor=user)
        order.refresh_from_db()
        assert order.delivery_status == DeliveryStatus.DELIVERED
        assert order.order_status == OrderStatus.COMPLETED
        assert mock_whatsapp.called

    @patch("apps.orders.services._send_whatsapp_with_snapshot")
    def test_cancel_order(self, mock_whatsapp, tenant, user, customer):
        """Testa o cancelamento de um pedido."""
        order = Order.objects.create(
            tenant=tenant,
            customer=customer,
            seller=user,
            total_value=50.00,
            delivery_address="Rua debaixo, 0"
        )

        OrderStatusService().cancel_order(order=order, actor=user, reason="Arrependimento")
        order.refresh_from_db()

        assert order.order_status == OrderStatus.CANCELLED
        assert order.cancel_reason == "Arrependimento"
        assert mock_whatsapp.called

@pytest.mark.django_db
class TestOrderUtilities:
    def test_parse_brazilian_decimal(self):
        from decimal import Decimal

        from apps.orders.services import parse_brazilian_decimal
        assert parse_brazilian_decimal("R$ 1.250,55") == Decimal("1250.55")
        assert parse_brazilian_decimal("150,00") == Decimal("150.00")
        assert parse_brazilian_decimal("2.500,00") == Decimal("2500.00")
        assert parse_brazilian_decimal("") == Decimal("0.00")
        with pytest.raises(ValueError, match="Valor monetário inválido"):
            parse_brazilian_decimal("abc")

    def test_validate_cpf(self):
        from apps.orders.services import validate_cpf
        assert validate_cpf("111.444.777-35") is True
        assert validate_cpf("12345678901") is False
        assert validate_cpf("00000000000") is False

@pytest.mark.django_db
class TestExtendedWorkflow:
    def test_failed_delivery_attempts(self, tenant, user, customer):
        """Testa o incremento de tentativas de entrega."""
        # Cria e envia via Serviço para garantir estado válido
        order = Order.objects.create(
            tenant=tenant, customer=customer, seller=user,
            total_value=100.00, delivery_address="Teste",
            delivery_type="motoboy"
        )
        OrderStatusService().mark_as_shipped(order=order, actor=user)

        OrderStatusService().mark_failed_attempt(order=order, actor=user, reason="Destinatário ausente")
        order.refresh_from_db()
        assert order.delivery_status == DeliveryStatus.FAILED_ATTEMPT
        assert order.delivery_attempts == 1

        # Simula volta para SHIPPED antes de nova falha (lógica do service exige SHIPPED)
        order.delivery_status = DeliveryStatus.SHIPPED
        order.save()

        OrderStatusService().mark_failed_attempt(order=order, actor=user, reason="Endereço não localizado")
        order.refresh_from_db()
        assert order.delivery_attempts == 2

    def test_pickup_workflow(self, tenant, user, customer):
        """Testa o fluxo de retirada: Pronto -> Retirado."""
        order = Order.objects.create(
            tenant=tenant, customer=customer, seller=user,
            total_value=80.00, delivery_type="pickup"
        )

        OrderStatusService().mark_ready_for_pickup(order=order, actor=user)
        order.refresh_from_db()
        assert order.delivery_status == DeliveryStatus.READY_FOR_PICKUP
        assert order.pickup_code is not None
        assert len(order.pickup_code) == 4

        OrderStatusService().mark_as_picked_up(order=order, actor=user)
        order.refresh_from_db()
        assert order.delivery_status == DeliveryStatus.PICKED_UP
        assert order.order_status == OrderStatus.COMPLETED

    def test_return_order_with_status_check(self, tenant, user, customer):
        """Testa a devolução de um pedido concluído."""
        order = Order.objects.create(
            tenant=tenant, customer=customer, seller=user,
            total_value=200.00, delivery_address="Teste",
            delivery_status=DeliveryStatus.DELIVERED,
            order_status=OrderStatus.COMPLETED,
            payment_status=PaymentStatus.PAID
        )

        OrderStatusService().return_order(order=order, actor=user, reason="Defeito", refund=True)
        order.refresh_from_db()
        assert order.order_status == OrderStatus.RETURNED
        assert order.payment_status == PaymentStatus.REFUNDED
        assert order.return_reason == "Defeito"

    def test_change_delivery_type_logic(self, tenant, user, customer):
        """Testa a mudança de tipo de entrega."""
        order = Order.objects.create(
            tenant=tenant, customer=customer, seller=user,
            total_value=120.00, delivery_type="pickup",
            delivery_status=DeliveryStatus.READY_FOR_PICKUP
        )

        OrderStatusService().change_delivery_type(
            order=order, actor=user, new_type="motoboy",
            address="Av Central, 500"
        )

        order.refresh_from_db()
        assert order.delivery_type == "motoboy"
        assert order.delivery_status == DeliveryStatus.PENDING
