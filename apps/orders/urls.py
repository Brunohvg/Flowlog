"""
URLs do app orders - Flowlog.
"""

from django.urls import path

from .views import (
    order_cancel,
    order_create,
    order_detail,
    order_edit,
    order_label,
    order_list,
    order_mark_delivered,
    order_mark_paid,
    order_mark_picked_up,
    order_mark_shipped,
    order_ready_for_pickup,
)

urlpatterns = [
    # Lista e criação
    path("", order_list, name="order_list"),
    path("novo/", order_create, name="order_create"),
    
    # Detalhe e edição
    path("<uuid:order_id>/", order_detail, name="order_detail"),
    path("<uuid:order_id>/editar/", order_edit, name="order_edit"),
    
    # Pagamento
    path("<uuid:order_id>/pagar/", order_mark_paid, name="order_mark_paid"),
    
    # Fluxo de entrega
    path("<uuid:order_id>/enviar/", order_mark_shipped, name="order_mark_shipped"),
    path("<uuid:order_id>/entregar/", order_mark_delivered, name="order_mark_delivered"),
    
    # Fluxo de retirada
    path("<uuid:order_id>/liberar-retirada/", order_ready_for_pickup, name="order_ready_for_pickup"),
    path("<uuid:order_id>/retirado/", order_mark_picked_up, name="order_mark_picked_up"),
    
    # Cancelamento
    path("<uuid:order_id>/cancelar/", order_cancel, name="order_cancel"),
    
    # Impressão
    path("<uuid:order_id>/etiqueta/", order_label, name="order_label"),
]
