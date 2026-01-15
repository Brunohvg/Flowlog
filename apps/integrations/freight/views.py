"""
Views para cálculo de frete.
"""

import json
import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from apps.integrations.freight.services import FreightCalculator

logger = logging.getLogger(__name__)


@login_required
@require_GET
def freight_calculator(request):
    """Página de cálculo de frete."""
    settings = getattr(request.tenant, "settings", None)

    context = {
        "store_cep": settings.store_cep if settings else "",
        "correios_enabled": settings.correios_enabled if settings else False,
        "motoboy_price_per_km": settings.motoboy_price_per_km if settings else 0,
        "motoboy_min_price": settings.motoboy_min_price if settings else 0,
        "motoboy_max_price": settings.motoboy_max_price if settings else None,
    }

    return render(request, "freight/calculator.html", context)


@login_required
@require_POST
def freight_calculate_api(request):
    """API para cálculo de frete (AJAX)."""
    settings = getattr(request.tenant, "settings", None)

    if not settings:
        return JsonResponse({"success": False, "error": "Configurações não encontradas"}, status=400)

    if not settings.store_cep:
        return JsonResponse({"success": False, "error": "CEP da loja não configurado"}, status=400)

    try:
        data = json.loads(request.body) if request.body else {}
        cep_destino = data.get("cep_destino", "").strip()
        peso = data.get("peso", 0.3)
    except json.JSONDecodeError:
        cep_destino = request.POST.get("cep_destino", "").strip()
        peso = request.POST.get("peso", 0.3)

    if not cep_destino:
        return JsonResponse({"success": False, "error": "CEP de destino obrigatório"}, status=400)

    # Converter peso
    try:
        peso = float(str(peso).replace(',', '.'))
    except (ValueError, TypeError):
        peso = 0.3

    # Limpar CEP
    cep_clean = "".join(filter(str.isdigit, cep_destino))
    if len(cep_clean) != 8:
        return JsonResponse({"success": False, "error": "CEP inválido (deve ter 8 dígitos)"}, status=400)

    try:
        calculator = FreightCalculator(settings)
        result = calculator.calculate_all(cep_destino, peso=peso)

        response_data = {
            "success": True,
            "cep_destino": cep_destino,
            "cep_origem": settings.store_cep,
            "correios": [],
            "motoboy": None,
            "distance_km": result.get("distance_km"),
        }

        # Formatar resultados Correios
        for freight in result.get("correios", []):
            response_data["correios"].append({
                "service": freight.service_name,
                "code": freight.service_code,
                "price": str(freight.price) if not freight.error else None,
                "delivery_days": freight.delivery_days if not freight.error else None,
                "error": freight.error,
            })

        # Mandaê
        response_data["mandae"] = []
        for rate in result.get("mandae", []):
            response_data["mandae"].append({
                "service": rate.get("name"),
                "price": str(rate.get("price")),
                "delivery_days": rate.get("days"),
                "error": None,
            })

        # Motoboy
        motoboy_result = result.get("motoboy")
        if motoboy_result:
            # Pode ser um dict com price ou com error
            if isinstance(motoboy_result, dict):
                if motoboy_result.get("error"):
                    response_data["motoboy"] = {
                        "price": None,
                        "distance_km": motoboy_result.get("distance_km"),
                        "error": motoboy_result.get("error"),
                    }
                else:
                    response_data["motoboy"] = {
                        "price": str(motoboy_result.get("price")),
                        "distance_km": motoboy_result.get("distance_km"),
                        "delivery_time": "Mesmo dia",
                    }
            else:
                # Valor simples (Decimal)
                response_data["motoboy"] = {
                    "price": str(motoboy_result),
                    "distance_km": result.get("distance_km"),
                    "delivery_time": "Mesmo dia",
                }

        # Info do CEP
        if result.get("cep_info"):
            cep_info = result["cep_info"]
            response_data["cep_info"] = {
                "street": cep_info.street,
                "neighborhood": cep_info.neighborhood,
                "city": cep_info.city,
                "state": cep_info.state,
            }

        return JsonResponse(response_data)

    except Exception as e:
        logger.exception("Erro ao calcular frete")
        return JsonResponse({"success": False, "error": f"Erro interno: {e}"}, status=500)
