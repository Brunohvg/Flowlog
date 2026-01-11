import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("tenants", "0006_pagarme_fields"),
        ("orders", "0005_order_motoboy_fields"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PaymentLink",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="Criado em"),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="Atualizado em"),
                ),
                (
                    "pagarme_order_id",
                    models.CharField(
                        blank=True,
                        help_text="Order ID retornado pela API",
                        max_length=100,
                        verbose_name="ID do Pedido Pagar.me",
                    ),
                ),
                (
                    "pagarme_charge_id",
                    models.CharField(
                        blank=True,
                        help_text="Charge ID para rastreamento",
                        max_length=100,
                        verbose_name="ID da Cobrança",
                    ),
                ),
                (
                    "checkout_url",
                    models.URLField(
                        blank=True,
                        help_text="Link para pagamento",
                        verbose_name="URL do Checkout",
                    ),
                ),
                (
                    "amount",
                    models.DecimalField(
                        decimal_places=2, max_digits=10, verbose_name="Valor"
                    ),
                ),
                (
                    "installments",
                    models.PositiveIntegerField(default=1, verbose_name="Parcelas"),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pendente"),
                            ("paid", "Pago"),
                            ("canceled", "Cancelado"),
                            ("failed", "Falhou"),
                        ],
                        default="pending",
                        max_length=20,
                        verbose_name="Status",
                    ),
                ),
                ("description", models.TextField(blank=True, verbose_name="Descrição")),
                (
                    "customer_name",
                    models.CharField(
                        blank=True, max_length=200, verbose_name="Nome do Cliente"
                    ),
                ),
                (
                    "customer_email",
                    models.EmailField(
                        blank=True, max_length=254, verbose_name="Email do Cliente"
                    ),
                ),
                (
                    "customer_phone",
                    models.CharField(
                        blank=True, max_length=20, verbose_name="Telefone do Cliente"
                    ),
                ),
                (
                    "expires_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="Expira em"
                    ),
                ),
                (
                    "paid_at",
                    models.DateTimeField(blank=True, null=True, verbose_name="Pago em"),
                ),
                (
                    "webhook_data",
                    models.JSONField(
                        blank=True, default=dict, verbose_name="Dados do Webhook"
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="payment_links_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "order",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="payment_links",
                        to="orders.order",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="payment_links",
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "verbose_name": "Link de Pagamento",
                "verbose_name_plural": "Links de Pagamento",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="paymentlink",
            index=models.Index(
                fields=["tenant", "status"], name="payments_pa_tenant__7f5c8e_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="paymentlink",
            index=models.Index(
                fields=["pagarme_order_id"], name="payments_pa_pagarme_8e2f3a_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="paymentlink",
            index=models.Index(
                fields=["pagarme_charge_id"], name="payments_pa_pagarme_c1d9e2_idx"
            ),
        ),
    ]
