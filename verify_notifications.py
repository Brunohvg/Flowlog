
import os
import sys
import django
from unittest.mock import patch, MagicMock
import json

# Setup Django
sys.path.append("/home/vidal/Projetos/Flowlog")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from apps.orders.models import Order, DeliveryType, OrderStatus
from apps.orders.services import OrderStatusService, OrderService
from apps.tenants.models import Tenant
from django.contrib.auth import get_user_model

User = get_user_model()

def verify():
    print("--- Verificando Notificações Automatizadas ---")

    # 1. Setup Data
    tenant = Tenant.objects.first()
    if not tenant:
        print("FAIL: Nenhum tenant encontrado")
        return

    user = User.objects.filter(tenant=tenant).first()
    if not user:
        print("FAIL: Nenhum usuário encontrado")
        return

    from apps.orders.models import Order, DeliveryType, OrderStatus, Customer

    # Create dummy customer
    customer, _ = Customer.objects.get_or_create(
        tenant=tenant,
        phone="5511999999999",
        defaults={"name": "Teste Notificacao"}
    )

    # Create dummy order
    order = Order.objects.create(
        tenant=tenant,
        customer=customer,
        seller=user,
        total_value=100.00,
        delivery_type=DeliveryType.SEDEX,
        delivery_address="Rua Teste, 123"
    )
    print(f"Pedido criado: {order.code}")

    # 2. Test Automated Notification (Mark as Shipped)
    print("\nTestando Notificação Automática (Enviado)...")

    # Force Broker URL
    from django.conf import settings
    # Hack to allow setting attribute on settings object if it doesn't exist or is immutable-ish
    # But often in scripts this assignment works. If not, we use patch.
    try:
        settings.CELERY_BROKER_URL = "redis://mock"
    except Exception:
        pass

    # Patches
    # 1. Mock celery task
    # 2. Mock transaction.on_commit to run immediately (script doesn't use real transaction loop)
    # 3. Mock settings just in case assignment failed

    with patch('apps.orders.services.send_whatsapp_notification.apply_async') as mock_task, \
         patch('django.db.transaction.on_commit', side_effect=lambda func: func()), \
         patch.object(settings, 'CELERY_BROKER_URL', 'redis://mock', create=True):

        # Action
        OrderStatusService().mark_as_shipped(order=order, actor=user, tracking_code="TEST123BR")

        # Verify
        if mock_task.called:
            print("OK: Task do Celery chamada.")
            # apply_async(args=[...], ...) -> call_args.kwargs['args']
            call_kwargs = mock_task.call_args.kwargs
            task_args = call_kwargs.get('args', [])

            if not task_args:
                 # Fallback if called positonally (unlikely for apply_async but safety)
                 if mock_task.call_args.args:
                     task_args = mock_task.call_args.args[0]

            snapshot_json = task_args[0]
            method = task_args[1]

            print(f"Método chamado: {method}")
            snapshot = json.loads(snapshot_json)
            print(f"Snapshot keys: {list(snapshot.keys())}")
            # print(f"Snapshot ID: {snapshot['id']}")
            print(f"Snapshot Status: {snapshot.get('delivery_status') or snapshot.get('status')}")

            status = snapshot.get('delivery_status') or snapshot.get('status')
            if method == "send_order_shipped" and status == "shipped":
                print("SUCCESS: Notificação de envio enfileirada corretamente.")
            else:
                print("FAIL: Dados da notificação incorretos.")
        else:
            print("FAIL: Task do Celery NÃO foi chamada.")

    # Debug Settings
    from django.conf import settings
    print(f"DEBUG: CELERY_BROKER_URL = '{getattr(settings, 'CELERY_BROKER_URL', 'N/A')}'")

    # 3. Test Manual Resend
    print("\nTestando Reenvio Manual...")
    with patch('apps.orders.services.send_whatsapp_notification.apply_async') as mock_task, \
         patch('django.db.transaction.on_commit', side_effect=lambda func: func()), \
         patch.object(settings, 'CELERY_BROKER_URL', 'redis://mock', create=True):
        # Action
        OrderStatusService().resend_notification(order=order, notification_type="shipped")

        # Verify
        if mock_task.called:
             print("OK: Task do Celery chamada (Reenvio).")
             print("SUCCESS: Reenvio manual funcionou via Snapshot.")
        else:
             print("FAIL: Task do Celery NÃO foi chamada no reenvio.")

    # Cleanup
    order.delete()

if __name__ == "__main__":
    verify()
