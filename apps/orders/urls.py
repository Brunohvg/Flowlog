from django.urls import path

from .views import (
    order_create,
    order_label,
    order_list,
    order_mark_delivered,
    order_mark_shipped,
    order_ready_for_pickup,
)

urlpatterns = [
    # Lista e criação
    path("", order_list, name="order_list"),
    path("novo/", order_create, name="order_create"),
    # Fluxo de entrega
    path(
        "<uuid:order_id>/enviar/",
        order_mark_shipped,
        name="order_mark_shipped",
    ),
    path(
        "<uuid:order_id>/entregar/",
        order_mark_delivered,
        name="order_mark_delivered",
    ),
    # Fluxo de retirada
    path(
        "<uuid:order_id>/retirada/",
        order_ready_for_pickup,
        name="order_ready_for_pickup",
    ),
    # Impressão
    path(
        "<uuid:order_id>/etiqueta/",
        order_label,
        name="order_label",
    ),
]
