"""
URLs do módulo de frete.
"""

from django.urls import path

from apps.integrations.freight import views

urlpatterns = [
    path("calcular-frete/", views.freight_calculator, name="freight_calculator"),
    path(
        "api/calcular-frete/", views.freight_calculate_api, name="freight_calculate_api"
    ),
]
