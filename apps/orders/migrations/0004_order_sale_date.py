# Generated manually for sale_date field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0003_rename_orders_orde_pickup__7ab123_idx_orders_orde_pickup__550cbd_idx'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='sale_date',
            field=models.DateField(
                blank=True, 
                null=True, 
                verbose_name='Data da Venda',
                help_text='Data efetiva da venda (default: data de criação)'
            ),
        ),
        migrations.AddIndex(
            model_name='order',
            index=models.Index(fields=['tenant', 'sale_date'], name='orders_orde_tenant__sale_idx'),
        ),
    ]
