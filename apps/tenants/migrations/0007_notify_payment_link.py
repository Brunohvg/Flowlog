from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0006_pagarme_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='tenantsettings',
            name='notify_payment_link',
            field=models.BooleanField(default=True, verbose_name='Notificar: Link de Pagamento'),
        ),
        migrations.AddField(
            model_name='tenantsettings',
            name='msg_payment_link',
            field=models.TextField(
                blank=True,
                default=(
                    "Olá {nome}! 💳\n\n"
                    "Segue o link de pagamento do pedido *{codigo}*:\n\n"
                    "💰 Valor: R$ {valor}\n"
                    "🔗 {link_pagamento}\n\n"
                    "O link expira em 12 horas.\n\n"
                    "_{loja}_"
                ),
                help_text='Placeholders: {nome}, {codigo}, {valor}, {link_pagamento}, {loja}',
                verbose_name='Mensagem: Link de Pagamento',
            ),
        ),
    ]
