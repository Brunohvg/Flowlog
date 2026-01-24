"""
URLs do módulo WhatsApp: Setup e configuração da instância.
"""

from django.urls import path

from . import views

urlpatterns = [
    path("", views.whatsapp_setup, name="whatsapp_setup"),
    path("salvar/", views.whatsapp_save_config, name="whatsapp_save_config"),
    path(
        "criar-instancia/",
        views.whatsapp_create_instance,
        name="whatsapp_create_instance",
    ),
    path("qrcode/", views.whatsapp_get_qrcode, name="whatsapp_get_qrcode"),
    path("status/", views.whatsapp_check_status, name="whatsapp_check_status"),
    path("desconectar/", views.whatsapp_disconnect, name="whatsapp_disconnect"),
    path("testar/", views.whatsapp_test_message, name="whatsapp_test_message"),
]
