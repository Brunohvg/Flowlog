"""
Migration para adicionar campos de rastreio e timestamps de entrega.
Também atualiza DeliveryType para incluir motoboy, sedex, pac.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0003_alter_order_delivery_status'),
    ]

    operations = [
        # Adiciona campo tracking_code
        migrations.AddField(
            model_name='order',
            name='tracking_code',
            field=models.CharField(
                blank=True,
                help_text='Obrigatório para SEDEX e PAC',
                max_length=50,
                verbose_name='Código de Rastreio',
            ),
        ),
        
        # Adiciona campo shipped_at
        migrations.AddField(
            model_name='order',
            name='shipped_at',
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name='Enviado em',
            ),
        ),
        
        # Adiciona campo delivered_at
        migrations.AddField(
            model_name='order',
            name='delivered_at',
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name='Entregue em',
            ),
        ),
        
        # Atualiza choices de delivery_type para incluir motoboy, sedex, pac
        migrations.AlterField(
            model_name='order',
            name='delivery_type',
            field=models.CharField(
                choices=[
                    ('pickup', 'Retirada na Loja'),
                    ('motoboy', 'Motoboy'),
                    ('sedex', 'SEDEX'),
                    ('pac', 'PAC'),
                ],
                default='motoboy',
                max_length=20,
                verbose_name='Tipo de Entrega',
            ),
        ),
        
        # Atualiza choices de delivery_status para incluir picked_up
        migrations.AlterField(
            model_name='order',
            name='delivery_status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pendente'),
                    ('shipped', 'Enviado'),
                    ('delivered', 'Entregue'),
                    ('ready_for_pickup', 'Pronto para retirada'),
                    ('picked_up', 'Retirado'),
                ],
                default='pending',
                max_length=20,
                verbose_name='Status da Entrega',
            ),
        ),
        
        # Adiciona índices para tracking_code e delivery_type
        migrations.AddIndex(
            model_name='order',
            index=models.Index(
                fields=['tracking_code'],
                name='orders_orde_trackin_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='order',
            index=models.Index(
                fields=['tenant', 'delivery_type'],
                name='orders_orde_tenant__delivery_idx',
            ),
        ),
    ]
