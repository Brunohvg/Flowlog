"""
Views para webhooks da Mandaê.
"""

import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.tenants.models import TenantSettings

from .services import MandaeWebhookValidator, process_mandae_webhook

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def mandae_webhook(request):
    """
    Endpoint para receber webhooks da Mandaê.

    URL: /integrations/mandae/webhook/

    A Mandaê envia atualizações de status de envio para este endpoint.
    Requer configuração do webhook_secret nas configurações do tenant.
    """
    try:
        # Obter payload
        try:
            payload = json.loads(request.body)
        except json.JSONDecodeError:
            logger.warning("Webhook Mandaê: payload inválido")
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        # Extrair tracking code para identificar o tenant
        tracking_code = payload.get("trackingCode") or payload.get("tracking_code", "")

        if not tracking_code:
            logger.warning("Webhook Mandaê: sem código de rastreio")
            return JsonResponse({"error": "Missing tracking code"}, status=400)

        # Buscar o pedido para identificar o tenant
        from apps.orders.models import DeliveryType, Order

        try:
            order = Order.objects.select_related("tenant").get(
                tracking_code=tracking_code,
                delivery_type=DeliveryType.MANDAE,
            )
            tenant = order.tenant
        except Order.DoesNotExist:
            # Tentar identificar pelo prefixo do tracking
            # Formato típico: ATSNR + número
            tenant = None
            prefix = tracking_code[:5] if len(tracking_code) >= 5 else tracking_code

            settings_with_prefix = (
                TenantSettings.objects.filter(
                    mandae_tracking_prefix=prefix,
                    mandae_enabled=True,
                )
                .select_related("tenant")
                .first()
            )

            if settings_with_prefix:
                tenant = settings_with_prefix.tenant

            if not tenant:
                logger.warning(
                    "Webhook Mandaê: tenant não identificado para %s", tracking_code
                )
                # Retorna 200 para não reenviar (pode ser tracking de outro sistema)
                return JsonResponse({"status": "ignored", "reason": "unknown_tracking"})

        # Obter settings do tenant
        try:
            tenant_settings = tenant.settings
        except TenantSettings.DoesNotExist:
            logger.warning("Webhook Mandaê: tenant sem settings")
            return JsonResponse({"error": "Tenant not configured"}, status=400)

        # Validar assinatura (se configurado)
        signature = request.headers.get("X-Mandae-Signature", "")

        if not MandaeWebhookValidator.validate_signature(
            request.body,
            signature,
            tenant_settings.mandae_webhook_secret,
        ):
            logger.warning("Webhook Mandaê: assinatura inválida")
            return JsonResponse({"error": "Invalid signature"}, status=401)

        # Processar webhook
        result = process_mandae_webhook(payload, tenant)

        if result["processed"]:
            return JsonResponse(
                {
                    "status": "processed",
                    "order": result["order_code"],
                    "new_status": result["new_status"],
                }
            )
        else:
            return JsonResponse(
                {
                    "status": "ignored",
                    "reason": result["message"],
                }
            )

    except Exception as e:
        logger.exception("Erro ao processar webhook Mandaê: %s", e)
        return JsonResponse({"error": "Internal error"}, status=500)
