# Generated migration - Add CPF to Customer

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0004_add_tracking_and_timestamps'),
    ]

    operations = [
        migrations.AddField(
            model_name='customer',
            name='cpf',
            field=models.CharField(blank=True, help_text='CPF do cliente (usado para acompanhamento)', max_length=14, verbose_name='CPF'),
        ),
        migrations.AddField(
            model_name='customer',
            name='cpf_normalized',
            field=models.CharField(blank=True, db_index=True, editable=False, max_length=11, verbose_name='CPF Normalizado'),
        ),
        migrations.AddIndex(
            model_name='customer',
            index=models.Index(fields=['tenant', 'cpf_normalized'], name='orders_cust_tenant__a2b3c4_idx'),
        ),
    ]
