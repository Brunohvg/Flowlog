import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        # CORREÇÃO: Apontar para o arquivo correto de orders
        ("orders", "0006_rename_indices"),
        ("payments", "0004_remove_paymentlink_order_and_more"),
        ("tenants", "0006_pagarme_fields"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="paymentlink",
            options={
                "ordering": ["-created_at"],
                "verbose_name": "Link de Pagamento",
                "verbose_name_plural": "Links de Pagamento",
            },
        ),
        migrations.RemoveField(
            model_name="paymentlink",
            name="pagarme_checkout_id",
        ),
        migrations.AddField(
            model_name="paymentlink",
            name="order",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="payment_links",
                to="orders.order",
            ),
        ),
        migrations.AlterField(
            model_name="paymentlink",
            name="amount",
            field=models.DecimalField(
                decimal_places=2, max_digits=10, verbose_name="Valor"
            ),
        ),
        migrations.AlterField(
            model_name="paymentlink",
            name="checkout_url",
            field=models.URLField(
                blank=True,
                help_text="Link para pagamento",
                verbose_name="URL do Checkout",
            ),
        ),
        migrations.AlterField(
            model_name="paymentlink",
            name="customer_email",
            field=models.EmailField(blank=True, max_length=254, verbose_name="E-mail"),
        ),
        migrations.AlterField(
            model_name="paymentlink",
            name="customer_name",
            field=models.CharField(max_length=200, verbose_name="Nome do Cliente"),
        ),
        migrations.AlterField(
            model_name="paymentlink",
            name="customer_phone",
            field=models.CharField(blank=True, max_length=20, verbose_name="Telefone"),
        ),
        migrations.AlterField(
            model_name="paymentlink",
            name="description",
            field=models.CharField(max_length=200, verbose_name="Descrição"),
        ),
        migrations.AlterField(
            model_name="paymentlink",
            name="expires_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Expira em"),
        ),
        migrations.AlterField(
            model_name="paymentlink",
            name="installments",
            field=models.PositiveIntegerField(
                default=1, help_text="1 a 3 parcelas", verbose_name="Parcelas"
            ),
        ),
        migrations.AlterField(
            model_name="paymentlink",
            name="pagarme_charge_id",
            field=models.CharField(
                blank=True,
                help_text="Charge ID para rastreamento",
                max_length=100,
                verbose_name="ID da Cobrança",
            ),
        ),
        migrations.AlterField(
            model_name="paymentlink",
            name="pagarme_order_id",
            field=models.CharField(
                blank=True,
                help_text="Order ID retornado pela API",
                max_length=100,
                verbose_name="ID do Pedido Pagar.me",
            ),
        ),
        migrations.AlterField(
            model_name="paymentlink",
            name="paid_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Pago em"),
        ),
        migrations.AlterField(
            model_name="paymentlink",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Aguardando Pagamento"),
                    ("paid", "Pago"),
                    ("failed", "Falhou"),
                    ("canceled", "Cancelado"),
                    ("expired", "Expirado"),
                    ("refunded", "Estornado"),
                ],
                default="pending",
                max_length=20,
                verbose_name="Status",
            ),
        ),
        migrations.AlterField(
            model_name="paymentlink",
            name="webhook_data",
            field=models.JSONField(
                blank=True, default=dict, verbose_name="Dados do Webhook"
            ),
        ),
        migrations.AddIndex(
            model_name="paymentlink",
            index=models.Index(
                fields=["pagarme_order_id"], name="payments_pa_pagarme_8e579f_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="paymentlink",
            index=models.Index(
                fields=["pagarme_charge_id"], name="payments_pa_pagarme_9340ea_idx"
            ),
        ),
    ]
