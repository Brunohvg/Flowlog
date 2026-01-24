"""
Permissões customizadas da API.
"""

from rest_framework import permissions


class IsTenantUser(permissions.BasePermission):
    """Verifica se usuário pertence ao tenant da requisição."""

    message = "Você não tem acesso a este recurso."

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if not hasattr(request, "tenant"):
            return False
        return request.user.tenant_id == request.tenant.id


class IsTenantAdmin(permissions.BasePermission):
    """Verifica se usuário é admin do tenant."""

    message = "Apenas administradores podem realizar esta ação."

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if not hasattr(request, "tenant"):
            return False
        return request.user.tenant_id == request.tenant.id and request.user.is_staff
