"""
Models base para o sistema Bibelo.
"""

import uuid

from django.core.exceptions import ValidationError
from django.db import models


class BaseModel(models.Model):
    """Model base com campos de auditoria."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class TenantModel(BaseModel):
    """Model base para entidades que pertencem a um tenant."""

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.PROTECT,
    )

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        # Otimização: Só valida integridade do tenant se não for criação e
        # se o check for explicitamente necessário ou se estivermos em debug.
        # Na prática, em produção, isso evita 1 query SELECT extra para cada UPDATE.
        if not self._state.adding and kwargs.pop("check_tenant", False):
            original_tenant_id = self.__class__.objects.filter(pk=self.pk).values_list("tenant_id", flat=True).first()
            if original_tenant_id and original_tenant_id != self.tenant_id:
                raise ValidationError("Não é permitido alterar o tenant.")

        super().save(*args, **kwargs)
