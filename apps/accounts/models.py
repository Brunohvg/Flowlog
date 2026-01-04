"""
Models do app accounts.
"""

from django.contrib.auth.models import AbstractUser, BaseUserManager
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
    """Usuário do sistema."""

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
        null=True,  # 🔥 PERMITE SUPERUSER
        blank=True,
    )

    is_active = models.BooleanField("Ativo", default=True)

    objects = UserManager()  # 🔥 ESSENCIAL

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

    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN

    @property
    def is_seller(self):
        return self.role == self.Role.SELLER
