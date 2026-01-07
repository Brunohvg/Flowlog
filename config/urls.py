"""
URLs principais do Flowlog.

Estrutura:
    /                       → Dashboard (core)
    /<ADMIN_PATH>/          → Django Admin (configurável via env)
    /login/, /logout/       → Autenticação
    /pedidos/               → Gestão de pedidos (orders)
    /clientes/              → Gestão de clientes (customers)
    /rastreio/              → Rastreio público (tracking)
    /relatorios/            → Relatórios (core)
    /configuracoes/         → Configurações (core)
    /configuracoes/whatsapp/→ Setup WhatsApp (integrations)
    /perfil/                → Perfil do usuário (core)
"""

from decouple import config
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.http import JsonResponse
from django.urls import include, path

from apps.core.views import DashboardView


# =====================================================
# Healthcheck
# =====================================================
def healthcheck(request):
    """Endpoint simples para verificar se a aplicação está viva."""
    return JsonResponse({"status": "ok"})


# =====================================================
# Admin (rota configurável via variável de ambiente)
# =====================================================
ADMIN_PATH = config("DJANGO_ADMIN_PATH", default="admin/")

urlpatterns = [
    # ==========================================
    # Healthcheck
    # ==========================================
    path("healthcheck/", healthcheck, name="healthcheck"),

    # ==========================================
    # Admin
    # ==========================================
    path(ADMIN_PATH, admin.site.urls),

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

    # Pedidos
    path("pedidos/", include("apps.orders.urls")),

    # Clientes
    path("clientes/", include("apps.orders.customer_urls")),

    # Tracking público
    path("rastreio/", include("apps.orders.tracking_urls")),

    # WhatsApp
    path(
        "configuracoes/whatsapp/",
        include("apps.integrations.whatsapp.urls"),
    ),
]
