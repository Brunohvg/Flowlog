"""
Mixins reutilizáveis da API.
"""

from rest_framework import permissions

from apps.api.permissions import IsTenantUser


class TenantQuerySetMixin:
    """Filtra queryset por tenant automaticamente."""
    
    def get_queryset(self):
        qs = super().get_queryset()
        if hasattr(self.request, 'tenant'):
            return qs.filter(tenant=self.request.tenant)
        return qs.none()


class TenantCreateMixin:
    """Adiciona tenant automaticamente ao criar."""
    
    def perform_create(self, serializer):
        serializer.save(tenant=self.request.tenant)


class TenantViewSetMixin(TenantQuerySetMixin, TenantCreateMixin):
    """Combina filtro e criação com tenant."""
    
    permission_classes = [permissions.IsAuthenticated, IsTenantUser]
