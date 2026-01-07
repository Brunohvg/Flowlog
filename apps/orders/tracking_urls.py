"""
URLs do Tracking: Rastreio público de pedidos para clientes.
"""

from django.urls import path

from .tracking_views import (
    tracking_detail,
    tracking_login,
    tracking_logout,
    tracking_orders,
    tracking_search,
)

urlpatterns = [
    path("", tracking_search, name="tracking_search"),
    path("entrar/", tracking_login, name="tracking_login"),
    path("sair/", tracking_logout, name="tracking_logout"),
    path("meus-pedidos/", tracking_orders, name="tracking_orders"),
    path("<str:code>/", tracking_detail, name="tracking_detail"),
]
