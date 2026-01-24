# Generated manually - Flowlog v9
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="pickup_code",
            field=models.CharField(
                blank=True,
                null=True,
                help_text="Código de 4 dígitos gerado quando pedido fica pronto",
                max_length=6,
                verbose_name="Código de Retirada",
            ),
        ),
        migrations.AddIndex(
            model_name="order",
            index=models.Index(
                fields=["pickup_code"], name="orders_orde_pickup__7ab123_idx"
            ),
        ),
    ]
