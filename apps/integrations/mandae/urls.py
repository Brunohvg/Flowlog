"""
URLs para integração Mandaê.
"""

from django.urls import path

from . import views

app_name = "mandae"

urlpatterns = [
    path("webhook/", views.mandae_webhook, name="webhook"),
]
