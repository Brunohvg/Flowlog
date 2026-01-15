"""
Middleware para isolamento multi-tenant.
"""


from .context import set_current_tenant, clear_current_tenant

class TenantMiddleware:
    """Injeta tenant no request e no contexto global."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.tenant = None
        user = getattr(request, "user", None)

        token = None
        if user and user.is_authenticated:
            request.tenant = user.tenant
            token = set_current_tenant(user.tenant)

        try:
            response = self.get_response(request)
        finally:
            if token:
                clear_current_tenant(token)

        return response
