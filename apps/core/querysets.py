from django.core.exceptions import ImproperlyConfigured
from django.db import models

from .context import get_current_tenant


class TenantQuerySet(models.QuerySet):
    def for_tenant(self, tenant=None):
        tenant = tenant or get_current_tenant()
        if tenant is None:
            raise ImproperlyConfigured(
                "Tenant não informado e nenhum contexto global definido."
            )
        return self.filter(tenant=tenant)
