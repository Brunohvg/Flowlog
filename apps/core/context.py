from contextvars import ContextVar

# Variável de contexto para armazenar o tenant atual
_current_tenant = ContextVar("current_tenant", default=None)


def set_current_tenant(tenant):
    """Define o tenant para a requisição/thread atual."""
    return _current_tenant.set(tenant)


def get_current_tenant():
    """Recupera o tenant da requisição/thread atual."""
    return _current_tenant.get()


def clear_current_tenant(token=None):
    """Limpa o tenant atual."""
    if token:
        _current_tenant.reset(token)
    else:
        _current_tenant.set(None)
