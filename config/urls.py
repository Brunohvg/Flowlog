"""
URLs principais do Flowlog.

Estrutura:
    /                       → Dashboard (core)
    /admin/                 → Django Admin
    /login/, /logout/       → Autenticação
    /pedidos/               → Gestão de pedidos (orders)
    /clientes/              → Gestão de clientes (customers)
    /rastreio/              → Rastreio público (tracking)
    /relatorios/            → Relatórios (core)
    /configuracoes/         → Configurações (core)
    /configuracoes/whatsapp/→ Setup WhatsApp (integrations)
    /perfil/                → Perfil do usuário (core)
"""

from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.http import JsonResponse
from django.urls import include, path

from apps.core.views import DashboardView


def healthcheck(request):
    """Endpoint para verificar se o servidor está respondendo."""
    return JsonResponse({"status": "ok", "message": "Server is healthy"})


urlpatterns = [
    # ==========================================
    # Healthcheck
    # ==========================================
    path("healthcheck/", healthcheck, name="healthcheck"),

    # ==========================================
    # Admin
    # ==========================================
    path("admin/", admin.site.urls),
    
    # ==========================================
    # Autenticação
    # ==========================================
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="auth/login.html"),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    
    # ==========================================
    # Dashboard (raiz)
    # ==========================================
    path("", DashboardView.as_view(), name="dashboard"),
    
    # ==========================================
    # Apps - Rotas delegadas
    # ==========================================
    
    # Core: relatórios, configurações, perfil
    path("", include("apps.core.urls")),
    
    # Pedidos: CRUD completo
    path("pedidos/", include("apps.orders.urls")),
    
    # Clientes: listagem e detalhes
    path("clientes/", include("apps.orders.customer_urls")),
    
    # Tracking: rastreio público para clientes
    path("rastreio/", include("apps.orders.tracking_urls")),
    
    # WhatsApp: setup e configuração
    path("configuracoes/whatsapp/", include("apps.integrations.whatsapp.urls")),
]
