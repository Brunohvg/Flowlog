# Generated migration for notification and API logs

import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('tenants', '0001_initial'),
        ('orders', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='NotificationLog',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('correlation_id', models.CharField(db_index=True, help_text='ID de correlação para rastreamento de ponta a ponta', max_length=50)),
                ('celery_task_id', models.CharField(blank=True, db_index=True, help_text='ID da task Celery que originou o envio', max_length=100, null=True)),
                ('notification_type', models.CharField(choices=[
                    ('order_created', 'Pedido Criado'),
                    ('order_confirmed', 'Pedido Confirmado'),
                    ('payment_received', 'Pagamento Recebido'),
                    ('payment_refunded', 'Pagamento Estornado'),
                    ('order_shipped', 'Pedido Enviado'),
                    ('order_delivered', 'Pedido Entregue'),
                    ('delivery_failed', 'Entrega Falhou'),
                    ('ready_for_pickup', 'Pronto para Retirada'),
                    ('picked_up', 'Retirado'),
                    ('expired', 'Expirado'),
                    ('cancelled', 'Cancelado'),
                    ('returned', 'Devolvido'),
                ], db_index=True, max_length=50)),
                ('status', models.CharField(choices=[
                    ('pending', 'Pendente'),
                    ('sent', 'Enviado'),
                    ('failed', 'Falhou'),
                    ('blocked', 'Bloqueado'),
                ], db_index=True, default='pending', max_length=20)),
                ('recipient_phone', models.CharField(help_text='Últimos 4 dígitos do telefone', max_length=20)),
                ('recipient_name', models.CharField(blank=True, max_length=200)),
                ('message_preview', models.TextField(blank=True, help_text='Preview da mensagem (truncado)', max_length=500)),
                ('api_response', models.JSONField(blank=True, help_text='Resposta completa da Evolution API', null=True)),
                ('error_message', models.TextField(blank=True)),
                ('error_code', models.CharField(blank=True, max_length=50)),
                ('retry_count', models.PositiveSmallIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('sent_at', models.DateTimeField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notification_logs', to='tenants.tenant')),
                ('order', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='notification_logs', to='orders.order')),
            ],
            options={
                'verbose_name': 'Log de Notificação',
                'verbose_name_plural': 'Logs de Notificações',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='APIRequestLog',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('correlation_id', models.CharField(db_index=True, help_text='ID de correlação para rastreamento', max_length=50)),
                ('method', models.CharField(max_length=10)),
                ('endpoint', models.CharField(max_length=500)),
                ('instance_name', models.CharField(blank=True, max_length=100, null=True)),
                ('request_body', models.JSONField(blank=True, null=True)),
                ('status_code', models.IntegerField(default=0)),
                ('response_body', models.JSONField(blank=True, null=True)),
                ('response_time_ms', models.IntegerField(default=0, help_text='Tempo de resposta em milissegundos')),
                ('error_message', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={
                'verbose_name': 'Log de Requisição API',
                'verbose_name_plural': 'Logs de Requisições API',
                'ordering': ['-created_at'],
            },
        ),
        # Índices para NotificationLog
        migrations.AddIndex(
            model_name='notificationlog',
            index=models.Index(fields=['tenant', 'created_at'], name='integration_tenant__6d3a8e_idx'),
        ),
        migrations.AddIndex(
            model_name='notificationlog',
            index=models.Index(fields=['order', 'notification_type'], name='integration_order_i_a1b2c3_idx'),
        ),
        migrations.AddIndex(
            model_name='notificationlog',
            index=models.Index(fields=['status', 'created_at'], name='integration_status__d4e5f6_idx'),
        ),
        migrations.AddIndex(
            model_name='notificationlog',
            index=models.Index(fields=['notification_type', 'status'], name='integration_notific_g7h8i9_idx'),
        ),
        # Índices para APIRequestLog
        migrations.AddIndex(
            model_name='apirequestlog',
            index=models.Index(fields=['correlation_id', 'created_at'], name='integration_correla_j0k1l2_idx'),
        ),
        migrations.AddIndex(
            model_name='apirequestlog',
            index=models.Index(fields=['instance_name', 'created_at'], name='integration_instanc_m3n4o5_idx'),
        ),
        migrations.AddIndex(
            model_name='apirequestlog',
            index=models.Index(fields=['status_code', 'created_at'], name='integration_status__p6q7r8_idx'),
        ),
        migrations.AddIndex(
            model_name='apirequestlog',
            index=models.Index(fields=['endpoint', 'status_code'], name='integration_endpoin_s9t0u1_idx'),
        ),
    ]
