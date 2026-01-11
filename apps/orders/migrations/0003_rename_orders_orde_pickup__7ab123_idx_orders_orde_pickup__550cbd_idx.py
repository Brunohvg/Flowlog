from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0002_order_pickup_code"),
    ]

    operations = [
        migrations.RenameIndex(
            model_name="order",
            new_name="orders_orde_pickup__550cbd_idx",
            old_name="orders_orde_pickup__7ab123_idx",
        ),
    ]
