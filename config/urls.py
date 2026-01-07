"""
URLs principais do Flowlog.
"""

from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from apps.core.views import DashboardView, profile, reports, settings
from apps.orders.customer_views import customer_detail, customer_edit, customer_list
from apps.orders.tracking_views import (
    tracking_detail,
    tracking_login,
    tracking_logout,
    tracking_orders,
    tracking_search,
)
from apps.integrations.whatsapp.views import (
    whatsapp_setup,
    whatsapp_save_config,
    whatsapp_create_instance,
    whatsapp_get_qrcode,
    whatsapp_check_status,
    whatsapp_disconnect,
    whatsapp_test_message,
)

urlpatterns = [
    # Admin
    path("admin/", admin.site.urls),
    # Auth
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="auth/login.html"),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    # Dashboard
    path("", DashboardView.as_view(), name="dashboard"),
    # Relatórios
    path("relatorios/", reports, name="reports"),
    # Configurações
    path("configuracoes/", settings, name="settings"),
    # WhatsApp (sub-rotas de configuração)
    path("configuracoes/whatsapp/", whatsapp_setup, name="whatsapp_setup"),
    path("configuracoes/whatsapp/salvar/", whatsapp_save_config, name="whatsapp_save_config"),
    path("configuracoes/whatsapp/criar-instancia/", whatsapp_create_instance, name="whatsapp_create_instance"),
    path("configuracoes/whatsapp/qrcode/", whatsapp_get_qrcode, name="whatsapp_get_qrcode"),
    path("configuracoes/whatsapp/status/", whatsapp_check_status, name="whatsapp_check_status"),
    path("configuracoes/whatsapp/desconectar/", whatsapp_disconnect, name="whatsapp_disconnect"),
    path("configuracoes/whatsapp/testar/", whatsapp_test_message, name="whatsapp_test_message"),
    # Perfil
    path("perfil/", profile, name="profile"),
    # Clientes
    path("clientes/", customer_list, name="customer_list"),
    path("clientes/<uuid:customer_id>/", customer_detail, name="customer_detail"),
    path("clientes/<uuid:customer_id>/editar/", customer_edit, name="customer_edit"),
    # Orders
    path("pedidos/", include("apps.orders.urls")),
    # Tracking (público)
    path("rastreio/", tracking_search, name="tracking_search"),
    path("rastreio/entrar/", tracking_login, name="tracking_login"),
    path("rastreio/sair/", tracking_logout, name="tracking_logout"),
    path("rastreio/meus-pedidos/", tracking_orders, name="tracking_orders"),
    path("rastreio/<str:code>/", tracking_detail, name="tracking_detail"),
]
