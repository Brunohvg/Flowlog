from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0004_order_sale_date"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="motoboy_fee",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Valor pago ao motoboy pela entrega",
                max_digits=10,
                null=True,
                verbose_name="Valor Motoboy",
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="motoboy_paid",
            field=models.BooleanField(
                default=False,
                help_text="Se o motoboy já recebeu o pagamento",
                verbose_name="Motoboy Pago",
            ),
        ),
    ]
