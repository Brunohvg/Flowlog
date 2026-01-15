"""
URLs do app Core: Dashboard, Relatórios, Configurações e Perfil.
"""

from django.urls import path

from . import views

urlpatterns = [
    # Dashboard já está no config/urls.py como raiz
    path("relatorios/", views.reports, name="reports"),
    path("relatorios/csv/", views.reports_csv, name="reports_csv"),
    path("configuracoes/", views.settings, name="settings"),
    path("configuracoes/integracoes/", views.integrations_settings, name="integrations_settings"),
    path("configuracoes/integracoes/correios/", views.correios_settings, name="correios_settings"),
    path("configuracoes/integracoes/mandae/", views.mandae_settings, name="mandae_settings"),
    path("configuracoes/integracoes/pagarme/", views.pagarme_settings, name="pagarme_settings"),
    path("configuracoes/integracoes/motoboy/", views.motoboy_settings, name="motoboy_settings"),
    path("perfil/", views.profile, name="profile"),
]
