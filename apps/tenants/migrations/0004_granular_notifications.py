# Generated migration for granular notification control

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0003_alter_tenantsettings_msg_order_ready_for_pickup_and_more'),
    ]

    operations = [
        # Permitir null no evolution_instance para evitar conflitos de unique
        migrations.AlterField(
            model_name='tenantsettings',
            name='evolution_instance',
            field=models.CharField(
                blank=True,
                help_text='Nome único da instância (será criada automaticamente)',
                max_length=100,
                null=True,
                unique=True,
                verbose_name='Nome da Instância',
            ),
        ),
        
        # Adicionar campos de controle granular de notificações
        migrations.AddField(
            model_name='tenantsettings',
            name='notify_order_created',
            field=models.BooleanField(default=True, verbose_name='Notificar: Pedido Criado'),
        ),
        migrations.AddField(
            model_name='tenantsettings',
            name='notify_order_confirmed',
            field=models.BooleanField(default=False, verbose_name='Notificar: Pedido Confirmado'),
        ),
        migrations.AddField(
            model_name='tenantsettings',
            name='notify_payment_received',
            field=models.BooleanField(default=True, verbose_name='Notificar: Pagamento Recebido'),
        ),
        migrations.AddField(
            model_name='tenantsettings',
            name='notify_payment_refunded',
            field=models.BooleanField(default=True, verbose_name='Notificar: Pagamento Estornado'),
        ),
        migrations.AddField(
            model_name='tenantsettings',
            name='notify_order_shipped',
            field=models.BooleanField(default=True, verbose_name='Notificar: Pedido Enviado'),
        ),
        migrations.AddField(
            model_name='tenantsettings',
            name='notify_order_delivered',
            field=models.BooleanField(default=True, verbose_name='Notificar: Pedido Entregue'),
        ),
        migrations.AddField(
            model_name='tenantsettings',
            name='notify_delivery_failed',
            field=models.BooleanField(default=True, verbose_name='Notificar: Tentativa de Entrega Falha'),
        ),
        migrations.AddField(
            model_name='tenantsettings',
            name='notify_order_ready_for_pickup',
            field=models.BooleanField(default=True, verbose_name='Notificar: Pronto para Retirada'),
        ),
        migrations.AddField(
            model_name='tenantsettings',
            name='notify_order_picked_up',
            field=models.BooleanField(default=False, verbose_name='Notificar: Pedido Retirado'),
        ),
        migrations.AddField(
            model_name='tenantsettings',
            name='notify_order_expired',
            field=models.BooleanField(default=True, verbose_name='Notificar: Pedido Expirado'),
        ),
        migrations.AddField(
            model_name='tenantsettings',
            name='notify_order_cancelled',
            field=models.BooleanField(default=True, verbose_name='Notificar: Pedido Cancelado'),
        ),
        migrations.AddField(
            model_name='tenantsettings',
            name='notify_order_returned',
            field=models.BooleanField(default=True, verbose_name='Notificar: Pedido Devolvido'),
        ),
    ]
