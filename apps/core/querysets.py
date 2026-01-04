from django.core.exceptions import ImproperlyConfigured
from django.db import models


class TenantQuerySet(models.QuerySet):
    def for_tenant(self, tenant):
        if tenant is None:
            raise ImproperlyConfigured("Tenant não informado na query.")
        return self.filter(tenant=tenant)
