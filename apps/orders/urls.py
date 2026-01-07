"""
URLs do app Orders: CRUD de pedidos e ações.
"""

from django.urls import path

from .views import (
    order_cancel,
    order_change_delivery,
    order_create,
    order_detail,
    order_duplicate,
    order_edit,
    order_label,
    order_list,
    order_mark_delivered,
    order_mark_failed_attempt,
    order_mark_paid,
    order_mark_picked_up,
    order_mark_shipped,
    order_ready_for_pickup,
    order_resend_notification,
    order_return,
    validate_pickup_code,
    quick_pickup,
)

urlpatterns = [
    # Lista e criação
    path("", order_list, name="order_list"),
    path("novo/", order_create, name="order_create"),
    
    # Validação de código de retirada (API)
    path("validar-retirada/", validate_pickup_code, name="validate_pickup_code"),
    
    # Detalhe e edição
    path("<uuid:order_id>/", order_detail, name="order_detail"),
    path("<uuid:order_id>/editar/", order_edit, name="order_edit"),
    
    # Pagamento
    path("<uuid:order_id>/pagar/", order_mark_paid, name="order_mark_paid"),
    
    # Fluxo de entrega
    path("<uuid:order_id>/enviar/", order_mark_shipped, name="order_mark_shipped"),
    path("<uuid:order_id>/entregar/", order_mark_delivered, name="order_mark_delivered"),
    path("<uuid:order_id>/falha-entrega/", order_mark_failed_attempt, name="order_mark_failed_attempt"),
    
    # Fluxo de retirada
    path("<uuid:order_id>/liberar-retirada/", order_ready_for_pickup, name="order_ready_for_pickup"),
    path("<uuid:order_id>/retirado/", order_mark_picked_up, name="order_mark_picked_up"),
    path("<uuid:order_id>/retirada-rapida/", quick_pickup, name="quick_pickup"),
    
    # Cancelamento e devolução
    path("<uuid:order_id>/cancelar/", order_cancel, name="order_cancel"),
    path("<uuid:order_id>/devolver/", order_return, name="order_return"),
    
    # Alterações
    path("<uuid:order_id>/alterar-entrega/", order_change_delivery, name="order_change_delivery"),
    path("<uuid:order_id>/duplicar/", order_duplicate, name="order_duplicate"),
    path("<uuid:order_id>/reenviar-notificacao/", order_resend_notification, name="order_resend_notification"),
    
    # Impressão
    path("<uuid:order_id>/etiqueta/", order_label, name="order_label"),
]
