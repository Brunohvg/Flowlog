"""
Migration para adicionar campo de mensagem de retirada ao TenantSettings.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='tenantsettings',
            name='msg_order_ready_for_pickup',
            field=models.TextField(
                default=(
                    "Olá {nome}! 🏬\n\n"
                    "Seu pedido *{codigo}* está pronto para retirada!\n"
                    "Valor: R$ {valor}\n\n"
                    "Aguardamos você em nossa loja! 😊"
                ),
                help_text='Placeholders disponíveis: {nome}, {codigo}, {valor}',
                verbose_name='Mensagem: Pronto para Retirada',
            ),
        ),
    ]
