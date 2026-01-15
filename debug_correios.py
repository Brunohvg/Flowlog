
import os
import sys
import django
import logging

# Setup Django
sys.path.append("/home/vidal/Projetos/Flowlog")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from apps.integrations.correios.services import get_correios_client, CorreiosPricingClient
from apps.tenants.models import Tenant

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def debug():
    tenant = Tenant.objects.first()
    if not tenant:
        print("Nenhum tenant encontrado")
        return

    settings = tenant.settings
    print(f"Tenant: {tenant.name}")
    print(f"Auth Correios: User={settings.correios_usuario}, Contrato={settings.correios_contrato}")


    # clients = get_correios_client(settings)
    # _, tracking_client = clients
    # token = tracking_client.token

    token = "cws-ch1_JNp6V7SNrL3AHnlUEo6YXJ0YmliZWxvOjk5MTI0NjQ0MTg_MTpPdTA6sql8JQo7TzM6vSa"
    print(f"Token MANUAL: {token}")
    print(f"Token NOVO obtido: {token[:10]}...")

    pricing_client = CorreiosPricingClient(
        token=token,
        contrato=getattr(settings, 'correios_contrato', ''),
        cartao=getattr(settings, 'correios_cartao_postagem', '')
    )

    cep_origem = settings.store_cep
    cep_destino = "34600190" # Exemplo do user
    peso_gramas = 300 # 0.3kg

    print(f"\nCalculando Batch: Origem={cep_origem}, Destino={cep_destino}, Peso={peso_gramas}g")

    # Override methods to print raw response
    original_consultar_preco = pricing_client._consultar_preco

    def debug_consultar_preco(payload):
        print("\n--- Payload Preco ---")
        print(payload)
        resp = original_consultar_preco(payload)
        print("\n--- Response Preco ---")
        print(resp)
        return resp

    pricing_client._consultar_preco = debug_consultar_preco

    results = pricing_client.calculate_batch(
        cep_origem=cep_origem,
        cep_destino=cep_destino,
        peso_gramas=peso_gramas,
        produtos=["03220", "03298"]
    )

    print("\n--- Resultados Processados ---")
    for code, data in results.items():
        print(f"{code}: R$ {data['price']} - Dias: {data['days']} - Erro: {data['error']}")

if __name__ == "__main__":
    debug()
