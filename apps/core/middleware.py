"""
Middleware para isolamento multi-tenant.
"""


class TenantMiddleware:
    """Injeta tenant no request baseado no usuário autenticado."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.tenant = None

        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            request.tenant = user.tenant

        return self.get_response(request)
