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
        if not self._state.adding:
            original = self.__class__.objects.only("tenant_id").get(pk=self.pk)
            if original.tenant_id != self.tenant_id:
                raise ValidationError("Não é permitido alterar o tenant.")

        super().save(*args, **kwargs)
