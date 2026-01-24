"""
URLs do app payments
"""

from django.urls import path

from apps.payments import views

urlpatterns = [
    # Lista de links
    path("", views.payment_link_list, name="payment_link_list"),
    # Criar link avulso
    path("novo/", views.create_standalone_link, name="payment_link_create"),
    # Criar link do pedido (AJAX)
    path(
        "pedido/<uuid:order_id>/",
        views.create_link_for_order,
        name="create_link_for_order",
    ),
    # Detalhes
    path("<uuid:link_id>/", views.payment_link_detail, name="payment_link_detail"),
    # Webhook (sem autenticação - público)
    path("webhook/pagarme/", views.pagarme_webhook, name="pagarme_webhook"),
]
