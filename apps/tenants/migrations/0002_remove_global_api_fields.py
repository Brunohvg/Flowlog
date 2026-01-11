# Generated migration - Remove evolution_api_url and evolution_api_key from TenantSettings
# These are now global settings in settings.py
# Add instance token field for security

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0001_initial"),
    ]

    operations = [
        # Remove campos que agora são globais
        migrations.RemoveField(
            model_name="tenantsettings",
            name="evolution_api_url",
        ),
        migrations.RemoveField(
            model_name="tenantsettings",
            name="evolution_api_key",
        ),
        # Atualiza evolution_instance para ser único (null=True para permitir múltiplos vazios)
        migrations.AlterField(
            model_name="tenantsettings",
            name="evolution_instance",
            field=models.CharField(
                blank=True,
                null=True,
                help_text="Nome único da instância (será criada automaticamente)",
                max_length=100,
                unique=True,
                verbose_name="Nome da Instância",
            ),
        ),
        # Adiciona token individual da instância
        migrations.AddField(
            model_name="tenantsettings",
            name="evolution_instance_token",
            field=models.CharField(
                blank=True,
                null=True,
                help_text="Token individual da instância (gerado automaticamente)",
                max_length=200,
                verbose_name="Token da Instância",
            ),
        ),
    ]
