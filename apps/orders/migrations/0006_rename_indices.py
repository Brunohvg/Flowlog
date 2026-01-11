from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0005_order_motoboy_fields"),
    ]

    operations = [
        migrations.RenameIndex(
            model_name="order",
            new_name="orders_orde_tenant__9ec487_idx",
            old_name="orders_orde_tenant__sale_idx",
        ),
    ]
