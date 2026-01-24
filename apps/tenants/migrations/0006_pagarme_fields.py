# Generated manually - Add Pagar.me fields to TenantSettings

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0005_alter_tenantsettings_msg_delivery_failed_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenantsettings",
            name="pagarme_enabled",
            field=models.BooleanField(default=False, verbose_name="Pagar.me Ativo"),
        ),
        migrations.AddField(
            model_name="tenantsettings",
            name="pagarme_api_key",
            field=models.CharField(
                blank=True,
                help_text="Chave secreta do Pagar.me (sk_xxx)",
                max_length=200,
                verbose_name="Secret Key",
            ),
        ),
        migrations.AddField(
            model_name="tenantsettings",
            name="pagarme_max_installments",
            field=models.PositiveIntegerField(
                default=3, help_text="1 a 3 parcelas", verbose_name="Máximo de Parcelas"
            ),
        ),
        migrations.AddField(
            model_name="tenantsettings",
            name="pagarme_pix_enabled",
            field=models.BooleanField(
                default=False,
                help_text="Habilitar PIX como forma de pagamento (requer liberação na Pagar.me)",
                verbose_name="PIX Habilitado",
            ),
        ),
    ]
