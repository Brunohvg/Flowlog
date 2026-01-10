"""
URLs da API REST.

/api/v1/ - Versão 1
/api/docs/ - Swagger UI
/api/redoc/ - ReDoc
"""

from django.urls import path, include

from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

urlpatterns = [
    # Versão 1
    path("v1/", include("apps.api.v1.urls")),
    
    # Documentação
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]
