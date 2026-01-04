"""
URLs principais do Flowlog.
"""

from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from apps.core.views import dashboard, reports, settings, profile
from apps.orders.customer_views import customer_list, customer_detail, customer_edit
from apps.orders.tracking_views import tracking_search, tracking_detail

urlpatterns = [
    # Admin
    path("admin/", admin.site.urls),
    
    # Auth
    path("login/", auth_views.LoginView.as_view(template_name="auth/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    
    # Dashboard
    path("", dashboard, name="dashboard"),
    
    # Relatórios
    path("relatorios/", reports, name="reports"),
    
    # Configurações
    path("configuracoes/", settings, name="settings"),
    
    # Perfil
    path("perfil/", profile, name="profile"),
    
    # Clientes
    path("clientes/", customer_list, name="customer_list"),
    path("clientes/<uuid:customer_id>/", customer_detail, name="customer_detail"),
    path("clientes/<uuid:customer_id>/editar/", customer_edit, name="customer_edit"),
    
    # Orders
    path("pedidos/", include("apps.orders.urls")),
    
    # Tracking (público, sem login)
    path("rastreio/", tracking_search, name="tracking_search"),
    path("rastreio/<str:code>/", tracking_detail, name="tracking_detail"),
]
