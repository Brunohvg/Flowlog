"""
URLs do app Core: Dashboard, Relatórios, Configurações e Perfil.
"""

from django.urls import path

from . import views

urlpatterns = [
    # Dashboard já está no config/urls.py como raiz
    path("relatorios/", views.reports, name="reports"),
    path("configuracoes/", views.settings, name="settings"),
    path("perfil/", views.profile, name="profile"),
]
