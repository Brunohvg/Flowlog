from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        (
            "payments",
            "0002_rename_payments_pa_tenant__7f5c8e_idx_payments_pa_tenant__888fee_idx_and_more",
        ),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="paymentlink",
            options={"ordering": ["-created_at"]},
        ),
        migrations.RemoveIndex(
            model_name="paymentlink",
            name="payments_pa_pagarme_8e579f_idx",
        ),
        migrations.RemoveIndex(
            model_name="paymentlink",
            name="payments_pa_pagarme_9340ea_idx",
        ),
        migrations.AlterField(
            model_name="paymentlink",
            name="amount",
            field=models.DecimalField(decimal_places=2, max_digits=10),
        ),
        migrations.AlterField(
            model_name="paymentlink",
            name="checkout_url",
            field=models.URLField(blank=True),
        ),
        migrations.AlterField(
            model_name="paymentlink",
            name="customer_email",
            field=models.EmailField(blank=True, max_length=254),
        ),
        migrations.AlterField(
            model_name="paymentlink",
            name="customer_name",
            field=models.CharField(max_length=200),
        ),
        migrations.AlterField(
            model_name="paymentlink",
            name="customer_phone",
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AlterField(
            model_name="paymentlink",
            name="description",
            field=models.CharField(max_length=200),
        ),
        migrations.AlterField(
            model_name="paymentlink",
            name="expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="paymentlink",
            name="installments",
            field=models.PositiveSmallIntegerField(default=1),
        ),
        migrations.AlterField(
            model_name="paymentlink",
            name="pagarme_charge_id",
            field=models.CharField(blank=True, db_index=True, max_length=100),
        ),
        migrations.AlterField(
            model_name="paymentlink",
            name="pagarme_order_id",
            field=models.CharField(blank=True, db_index=True, max_length=100),
        ),
        migrations.AlterField(
            model_name="paymentlink",
            name="paid_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="paymentlink",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Aguardando"),
                    ("paid", "Pago"),
                    ("failed", "Falhou"),
                    ("canceled", "Cancelado"),
                    ("expired", "Expirado"),
                    ("refunded", "Estornado"),
                ],
                db_index=True,
                default="pending",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="paymentlink",
            name="webhook_data",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
