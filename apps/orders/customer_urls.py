"""
URLs de Clientes: Listagem, detalhes e edição.
"""

from django.urls import path

from .customer_views import (
    customer_csv,
    customer_detail,
    customer_edit,
    customer_list,
)

urlpatterns = [
    path("", customer_list, name="customer_list"),
    path("csv/", customer_csv, name="customer_csv"),
    path("<uuid:customer_id>/", customer_detail, name="customer_detail"),
    path("<uuid:customer_id>/editar/", customer_edit, name="customer_edit"),
]
