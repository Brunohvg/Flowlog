"""
Serviços de cálculo de frete - Correios e Motoboy.
"""

import logging
import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

import requests
from django.core.cache import cache
# Importação condicional para evitar ciclo se houver
from apps.integrations.correios.services import get_correios_client, CorreiosPricingClient

logger = logging.getLogger(__name__)


@dataclass
class FreightResult:
    """Resultado de um cálculo de frete."""
    service_name: str
    service_code: str
    price: Decimal
    delivery_days: int
    error: Optional[str] = None


@dataclass
class CepInfo:
    """Informações de um CEP."""
    cep: str
    street: str
    neighborhood: str
    city: str
    state: str
    lat: Optional[Decimal] = None
    lng: Optional[Decimal] = None


class ViaCepClient:
    """
    Cliente para consulta de CEP.
    Usa ViaCEP como primário e BrasilAPI como fallback.
    """

    VIACEP_URL = "https://viacep.com.br/ws"
    BRASILAPI_URL = "https://brasilapi.com.br/api/cep/v1"

    def get_cep_info(self, cep: str) -> Optional[CepInfo]:
        """Consulta informações de um CEP com fallback."""
        cep_clean = "".join(filter(str.isdigit, cep))
        if len(cep_clean) != 8:
            return None

        cache_key = f"cep_{cep_clean}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        # Tentar ViaCEP primeiro
        info = self._try_viacep(cep_clean)

        # Fallback para BrasilAPI
        if not info:
            info = self._try_brasilapi(cep_clean)

        if info:
            # Cache por 7 dias (CEPs raramente mudam)
            cache.set(cache_key, info, timeout=604800)

        return info

    def _try_viacep(self, cep: str) -> Optional[CepInfo]:
        """Tenta consultar no ViaCEP."""
        try:
            response = requests.get(
                f"{self.VIACEP_URL}/{cep}/json/",
                timeout=5
            )
            response.raise_for_status()
            data = response.json()

            if data.get("erro"):
                return None

            return CepInfo(
                cep=data.get("cep", ""),
                street=data.get("logradouro", ""),
                neighborhood=data.get("bairro", ""),
                city=data.get("localidade", ""),
                state=data.get("uf", ""),
            )
        except Exception as e:
            logger.warning("ViaCEP falhou: %s", e)
            return None

    def _try_brasilapi(self, cep: str) -> Optional[CepInfo]:
        """Fallback para BrasilAPI."""
        try:
            response = requests.get(
                f"{self.BRASILAPI_URL}/{cep}",
                timeout=5
            )
            response.raise_for_status()
            data = response.json()

            return CepInfo(
                cep=data.get("cep", ""),
                street=data.get("street", ""),
                neighborhood=data.get("neighborhood", ""),
                city=data.get("city", ""),
                state=data.get("state", ""),
            )
        except Exception as e:
            logger.warning("BrasilAPI falhou: %s", e)
            return None


class NominatimClient:
    """
    Cliente para geocoding.
    Usa Nominatim como primário e Photon (Komoot) como fallback.
    """

    NOMINATIM_URL = "https://nominatim.openstreetmap.org"
    PHOTON_URL = "https://photon.komoot.io"
    USER_AGENT = "Flowlog/1.0"

    def geocode_address(self, address: str) -> Optional[tuple[Decimal, Decimal]]:
        """Converte endereço em coordenadas lat/lng com fallback."""
        import hashlib
        address_hash = hashlib.md5(address.encode()).hexdigest()[:16]
        cache_key = f"geo_{address_hash}"

        cached = cache.get(cache_key)
        if cached:
            return cached

        # Tentar Nominatim primeiro
        result = self._try_nominatim(address)

        # Fallback para Photon
        if not result:
            result = self._try_photon(address)

        if result:
            # Cache por 30 dias (coordenadas não mudam)
            cache.set(cache_key, result, timeout=2592000)

        return result

    def _try_nominatim(self, address: str) -> Optional[tuple[Decimal, Decimal]]:
        """Tenta geocodificar via Nominatim."""
        try:
            response = requests.get(
                f"{self.NOMINATIM_URL}/search",
                params={
                    "q": address,
                    "format": "json",
                    "limit": 1,
                    "countrycodes": "br",
                },
                headers={"User-Agent": self.USER_AGENT},
                timeout=5,
            )
            response.raise_for_status()
            data = response.json()

            if not data:
                return None

            return (Decimal(data[0]["lat"]), Decimal(data[0]["lon"]))
        except Exception as e:
            logger.warning("Nominatim falhou: %s", e)
            return None

    def _try_photon(self, address: str) -> Optional[tuple[Decimal, Decimal]]:
        """Fallback para Photon (Komoot)."""
        try:
            response = requests.get(
                f"{self.PHOTON_URL}/api",
                params={
                    "q": f"{address}, Brasil",
                    "limit": 1,
                },
                timeout=5,
            )
            response.raise_for_status()
            data = response.json()

            features = data.get("features", [])
            if not features:
                return None

            coords = features[0].get("geometry", {}).get("coordinates", [])
            if len(coords) >= 2:
                # Photon retorna [lng, lat]
                return (Decimal(str(coords[1])), Decimal(str(coords[0])))
            return None
        except Exception as e:
            logger.warning("Photon falhou: %s", e)
            return None


def haversine_distance(
    lat1: Decimal, lng1: Decimal, lat2: Decimal, lng2: Decimal
) -> float:
    """
    Calcula a distância em km entre dois pontos usando a fórmula de Haversine.
    """
    R = 6371  # Raio da Terra em km

    lat1_rad = math.radians(float(lat1))
    lat2_rad = math.radians(float(lat2))
    delta_lat = math.radians(float(lat2 - lat1))
    delta_lng = math.radians(float(lng2 - lng1))

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


class CorreiosClient:
    """
    Cliente para cálculo de frete dos Correios.

    A API antiga (ws.correios.com.br) foi descontinuada.
    Esta implementação usa um fallback para estimativas baseadas em tabela.
    Para integração completa, use a nova API (api.correios.com.br) com autenticação.
    """

    # Códigos de serviço
    SEDEX = "04014"
    PAC = "04510"

    # Tabela de preços aproximados por região (fallback)
    # Baseado em faixas de CEP
    PRICE_TABLE = {
        # (min_cep, max_cep): (sedex_base, pac_base, sedex_days, pac_days)
        (10000000, 19999999): (35.0, 22.0, 2, 6),   # SP Capital
        (20000000, 29999999): (38.0, 24.0, 2, 7),   # RJ
        (30000000, 39999999): (36.0, 23.0, 2, 6),   # MG
        (40000000, 49999999): (45.0, 28.0, 4, 10),  # BA
        (50000000, 56999999): (48.0, 30.0, 5, 12),  # PE
        (57000000, 57999999): (50.0, 32.0, 5, 12),  # AL
        (58000000, 58999999): (48.0, 30.0, 5, 12),  # PB
        (59000000, 59999999): (50.0, 32.0, 6, 14),  # RN
        (60000000, 63999999): (52.0, 34.0, 6, 14),  # CE
        (64000000, 64999999): (55.0, 36.0, 7, 15),  # PI
        (65000000, 65999999): (55.0, 36.0, 7, 15),  # MA
        (66000000, 68899999): (58.0, 38.0, 8, 18),  # PA
        (69000000, 69299999): (60.0, 40.0, 10, 20), # AM
        (69300000, 69399999): (65.0, 45.0, 12, 25), # RR
        (69400000, 69899999): (60.0, 40.0, 10, 20), # AM
        (69900000, 69999999): (62.0, 42.0, 10, 22), # AC
        (70000000, 73699999): (42.0, 26.0, 3, 8),   # DF
        (74000000, 76799999): (45.0, 28.0, 4, 10),  # GO
        (76800000, 76999999): (55.0, 36.0, 6, 14),  # RO
        (77000000, 77999999): (50.0, 32.0, 5, 12),  # TO
        (78000000, 78899999): (48.0, 30.0, 5, 12),  # MT
        (79000000, 79999999): (45.0, 28.0, 4, 10),  # MS
        (80000000, 87999999): (40.0, 25.0, 3, 8),   # PR
        (88000000, 89999999): (42.0, 26.0, 3, 8),   # SC
        (90000000, 99999999): (45.0, 28.0, 4, 10),  # RS
    }

    def __init__(self, usuario: str = "", senha: str = "", contrato: str = ""):
        self.usuario = usuario
        self.senha = senha
        self.contrato = contrato

    def calcular_frete(
        self,
        cep_origem: str,
        cep_destino: str,
        peso: float = 0.3,
        comprimento: float = 16,
        altura: float = 2,
        largura: float = 11,
        servicos: list[str] = None,
    ) -> list[FreightResult]:
        """
        Calcula o frete para os serviços especificados.
        Usa estimativa por tabela de preços como fallback.
        """
        if servicos is None:
            servicos = [self.SEDEX, self.PAC]

        cep_destino_clean = "".join(filter(str.isdigit, cep_destino))

        results = []
        for servico in servicos:
            result = self._calcular_por_tabela(cep_destino_clean, servico, peso)
            results.append(result)

        return results

    def _calcular_por_tabela(
        self,
        cep_destino: str,
        servico: str,
        peso: float,
    ) -> FreightResult:
        """Calcula frete usando tabela de preços estimados."""
        service_names = {
            self.SEDEX: "SEDEX",
            self.PAC: "PAC",
        }

        try:
            cep_num = int(cep_destino)
        except ValueError:
            return FreightResult(
                service_name=service_names.get(servico, servico),
                service_code=servico,
                price=Decimal("0"),
                delivery_days=0,
                error="CEP inválido",
            )

        # Encontrar faixa de preço
        base_price = None
        delivery_days = 0

        for (min_cep, max_cep), prices in self.PRICE_TABLE.items():
            if min_cep <= cep_num <= max_cep:
                if servico == self.SEDEX:
                    base_price = prices[0]
                    delivery_days = prices[2]
                else:  # PAC
                    base_price = prices[1]
                    delivery_days = prices[3]
                break

        if base_price is None:
            # Fallback para CEP não mapeado
            if servico == self.SEDEX:
                base_price = 50.0
                delivery_days = 5
            else:
                base_price = 32.0
                delivery_days = 12

        # Ajustar por peso (adicional por kg acima de 0.3kg)
        if peso > 0.3:
            peso_extra = peso - 0.3
            adicional_por_kg = 8.0 if servico == self.SEDEX else 5.0
            base_price += peso_extra * adicional_por_kg

        return FreightResult(
            service_name=service_names.get(servico, servico) + " (estimativa)",
            service_code=servico,
            price=Decimal(str(round(base_price, 2))),
            delivery_days=delivery_days,
            error=None,
        )


class FreightCalculator:
    """Calculadora de frete unificada."""

    def __init__(self, tenant_settings):
        self.settings = tenant_settings
        self.viacep = ViaCepClient()
        self.nominatim = NominatimClient()
        self.correios = CorreiosClient(
            usuario=getattr(tenant_settings, 'correios_usuario', ''),
            senha=getattr(tenant_settings, 'correios_codigo_acesso', ''),
            contrato=getattr(tenant_settings, 'correios_contrato', ''),
        )

    def calculate_all(self, cep_destino: str, peso: float = 0.3) -> dict:
        """
        Calcula todas as opções de frete disponíveis.

        Returns:
            dict com 'correios', 'motoboy', e 'cep_info'
        """
        result = {
            "correios": [],
            "mandae": [],
            "motoboy": None,
            "cep_info": None,
            "distance_km": None,
        }

        # Validar CEP origem (loja)
        if not self.settings.store_cep:
            result["error"] = "CEP da loja não configurado"
            return result

        # Consultar CEP destino
        cep_info = self.viacep.get_cep_info(cep_destino)
        if cep_info:
            result["cep_info"] = cep_info

        # Calcular Correios
        if self.settings.correios_enabled:
            # Tentar via API CWS (Oficial) primeiro
            cws_results = self._calculate_correios_cws(cep_destino, peso)

            if cws_results:
                result["correios"] = cws_results
            else:
                # Fallback para Tabela Estimativa
                result["correios"] = self.correios.calcular_frete(
                    cep_origem=self.settings.store_cep,
                    cep_destino=cep_destino,
                    peso=peso,
                )

        # Calcular Mandaê
        if getattr(self.settings, "mandae_enabled", False) and getattr(self.settings, "mandae_token", None):
            from apps.integrations.mandae.services import MandaeClient

            mandae_client = MandaeClient(
                api_url=self.settings.mandae_api_url,
                token=self.settings.mandae_token,
                customer_id=self.settings.mandae_customer_id
            )

            mandae_rates = mandae_client.get_rates(cep_destino, [{"weight": peso, "quantity": 1}])
            if mandae_rates:
                result["mandae"] = mandae_rates

        # Calcular Motoboy por distância
        motoboy_result = self._calculate_motoboy(cep_destino, cep_info)
        if motoboy_result:
            result["motoboy"] = motoboy_result  # Dict completo (pode ter error)
            result["distance_km"] = motoboy_result.get("distance_km")

        return result

    def _calculate_correios_cws(self, cep_destino, peso_kg):
        """Calcula frete via API CWS (Oficial) usando Batch (Lote)."""
        try:
            clients = get_correios_client(self.settings)
            if not clients:
                return None

            _, tracking_client = clients
            token = tracking_client.token  # Reusa token do tracking

            pricing_client = CorreiosPricingClient(
                token=token,
                contrato=getattr(self.settings, 'correios_contrato', ''),
                cartao=getattr(self.settings, 'correios_cartao_postagem', '')
            )

            # Converter KG -> Gramas (API exige gramas e user passou 25000=25kg no exemplo)
            peso_gramas = int(peso_kg * 1000)
            if peso_gramas < 300: # Mínimo 300g (regra correios)
                peso_gramas = 300

            results = []

            # Serviços padrão
            services_map = {
                '03220': 'SEDEX',
                '03298': 'PAC'
            }
            codes = list(services_map.keys())

            # Chama API Batch
            batch_results = pricing_client.calculate_batch(
                cep_origem=self.settings.store_cep,
                cep_destino=cep_destino,
                peso_gramas=peso_gramas,
                produtos=codes
            )

            # Processa resultados
            valid_results_count = 0

            for code, data in batch_results.items():
                price = Decimal(str(data.get("price", 0)))
                days = data.get("days", 0)
                error = data.get("error", None)

                # Se o preço vier zerado e não tiver mensagem de erro explicita mas sabemos que falhou (como 403),
                # ou se simplesmente veio 0, vamos ignorar para permitir que o fallback (price table) assuma.
                # A menos que seja um erro de negócio ("CEP inválido"), aí talvez devêssemos mostrar.
                # Mas no caso do erro 403, 'error' vem vazio do calculate_batch e price 0.
                if price <= 0:
                    continue

                service_name = services_map.get(code, code)

                results.append(FreightResult(
                    service_name=service_name,
                    service_code=code,
                    price=price,
                    delivery_days=days,
                    error=error
                ))
                valid_results_count += 1

            # Se não obteve nenhum resultado válido, retorna None para ativar o Fallback (Tabela)
            if valid_results_count == 0:
                return None

            return results

        except Exception as e:
            logger.error("Erro CWS Batch: %s", e)
            return None

    def _calculate_motoboy(
        self, cep_destino: str, cep_info: Optional[CepInfo]
    ) -> Optional[dict]:
        """Calcula frete de motoboy baseado em distância."""
        # Verificar se temos coordenadas da loja
        if not self.settings.store_lat or not self.settings.store_lng:
            # Tentar geocodificar o CEP da loja
            store_cep_info = self.viacep.get_cep_info(self.settings.store_cep)
            if store_cep_info:
                address = f"{store_cep_info.street}, {store_cep_info.city}, {store_cep_info.state}, Brasil"
                coords = self.nominatim.geocode_address(address)
                if coords:
                    # Poderia salvar no settings aqui, mas isso é side-effect
                    store_lat, store_lng = coords
                else:
                    return None
            else:
                return None
        else:
            store_lat = self.settings.store_lat
            store_lng = self.settings.store_lng

        # Obter coordenadas do destino
        if cep_info:
            address = f"{cep_info.street}, {cep_info.city}, {cep_info.state}, Brasil"
            coords = self.nominatim.geocode_address(address)
            if not coords:
                return None
            dest_lat, dest_lng = coords
        else:
            return None

        # Calcular distância (haversine retorna float)
        distance_float = haversine_distance(store_lat, store_lng, dest_lat, dest_lng)
        distance = Decimal(str(distance_float))

        # Aplicar fator de correção (rota real ≈ 1.3x linha reta)
        distance_adjusted = distance * Decimal("1.3")

        # Verificar raio máximo (se configurado)
        max_radius = getattr(self.settings, 'motoboy_max_radius', None)
        if max_radius and distance_adjusted > max_radius:
            # Fora do raio de atendimento
            return {
                "price": None,
                "distance_km": round(float(distance_adjusted), 1),
                "error": f"Fora da área de atendimento (máx. {max_radius} km)",
            }

        # Calcular preço
        price = distance_adjusted * self.settings.motoboy_price_per_km

        # Aplicar mínimo
        if price < self.settings.motoboy_min_price:
            price = self.settings.motoboy_min_price

        # Aplicar máximo (se configurado)
        if self.settings.motoboy_max_price and price > self.settings.motoboy_max_price:
            price = self.settings.motoboy_max_price

        return {
            "price": price.quantize(Decimal("0.01")),
            "distance_km": round(float(distance_adjusted), 1),
        }
