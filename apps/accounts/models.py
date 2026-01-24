"""
Models do app accounts.

Refatorado v9:
- Validação clean() para garantir integridade tenant/role
- Superusers podem não ter tenant
- Sellers DEVEM ter tenant
"""

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import BaseModel


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("O e-mail é obrigatório.")

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", "admin")

        return self._create_user(email, password, **extra_fields)


class User(AbstractUser, BaseModel):
    """
    Usuário do sistema.

    Regras de integridade:
    - Superusers podem existir sem tenant (administradores do sistema)
    - Sellers DEVEM ter um tenant associado
    - Admins de tenant DEVEM ter um tenant associado
    """

    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        SELLER = "seller", "Vendedor"

    # REMOVE username
    username = None

    email = models.EmailField("E-mail", unique=True)

    role = models.CharField(
        "Perfil",
        max_length=20,
        choices=Role.choices,
        default=Role.SELLER,
    )

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.PROTECT,
        related_name="users",
        verbose_name="Empresa",
        null=True,  # Permite superusers sem tenant
        blank=True,
    )

    is_active = models.BooleanField("Ativo", default=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = "Usuário"
        verbose_name_plural = "Usuários"
        ordering = ["email"]
        indexes = [
            models.Index(fields=["tenant", "email"]),
        ]

    def __str__(self):
        return self.email

    def clean(self):
        """
        Validação de integridade: usuários não-superuser DEVEM ter tenant.
        """
        super().clean()

        # Superusers podem existir sem tenant (são admins do sistema)
        if self.is_superuser:
            return

        # Usuários normais (admin de tenant ou seller) DEVEM ter tenant
        if not self.tenant_id:
            raise ValidationError(
                {
                    "tenant": "Usuários não-superuser devem estar associados a uma empresa."
                }
            )

    def save(self, *args, **kwargs):
        # Executa validação antes de salvar
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN

    @property
    def is_seller(self):
        return self.role == self.Role.SELLER

    @property
    def can_access_admin(self):
        """Pode acessar área administrativa do tenant."""
        return self.is_admin or self.is_superuser
