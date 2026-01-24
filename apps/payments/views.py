"""
Views do app payments - Links de Pagamento
VERSÃO FINAL (produção-safe)
- Compatível com model atual
- Webhook determinístico
- Suporte a: paid, failed, expired, canceled, refunded
"""

import hashlib
import hmac
import json
import logging
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction  # <--- IMPORTANTE: Necessário para on_commit
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.orders.models import Order
from apps.payments.models import PaymentLink
from apps.payments.services import (
    PagarmeError,
    create_payment_link_for_order,
    create_standalone_payment_link,
)

logger = logging.getLogger(__name__)


# = : HELPERS
# ============================================================


def _is_valid_pagarme_signature(request, secret):
    """
    Verifica se a assinatura do Pagar.me é válida.
    Suporta sha256 (madrão v5) e sha1 (legado).
    """
    signature = request.headers.get("X-PagarMe-Signature")
    if not signature:
        return False

    if "=" in signature:
        algo, sig_hash = signature.split("=", 1)
    else:
        # Pagar.me v5 também pode enviar apenas o hash sha1 em algumas configs
        algo = "sha1"
        sig_hash = signature

    hash_obj = hashlib.sha256 if algo == "sha256" else hashlib.sha1
    expected = hmac.new(secret.encode(), request.body, hash_obj).hexdigest()
    return hmac.compare_digest(expected, sig_hash)


def _extract_pagarme_link_code(event_type: str, data: dict) -> str | None:
    """
    Extrai o ID do payment link (pl_...) dos eventos do Pagar.me.
    OBS: salvo em pagarme_order_id por compatibilidade com produção.
    """

    # Evento de expiração
    if event_type == "payment-link.expired":
        return data.get("id")

    # charge.* ou order.*
    if "code" in data:
        return data.get("code")

    order = data.get("order") or {}
    return order.get("code")


def _send_payment_link_whatsapp(payment_link):
    """Envia link de pagamento via WhatsApp (se Celery configurado)."""
    if not payment_link.order:
        return

    from django.conf import settings as django_settings

    if not getattr(django_settings, "CELERY_BROKER_URL", ""):
        return

    try:
        from apps.integrations.whatsapp.tasks import send_payment_link_whatsapp

        send_payment_link_whatsapp.apply_async(
            args=[str(payment_link.order.id), str(payment_link.id)],
            expires=300,
            ignore_result=True,
        )
    except Exception:
        logger.exception("Falha ao agendar WhatsApp link pagamento")


def _send_payment_confirmation_whatsapp(payment_link):
    """Envia WhatsApp de confirmação de pagamento."""
    if not payment_link.order:
        return

    tenant_settings = getattr(payment_link.tenant, "settings", None)
    if not tenant_settings or not tenant_settings.whatsapp_enabled:
        return
    if not tenant_settings.notify_payment_received:
        return

    from django.conf import settings as django_settings

    if not getattr(django_settings, "CELERY_BROKER_URL", ""):
        return

    try:
        from apps.integrations.whatsapp.tasks import send_payment_received_whatsapp

        send_payment_received_whatsapp.apply_async(
            args=[str(payment_link.order.id)],
            expires=300,
            ignore_result=True,
        )
    except Exception:
        logger.exception("Falha ao agendar WhatsApp confirmação pagamento")


def _send_payment_failed_whatsapp(payment_link):
    """Envia WhatsApp quando pagamento falha."""
    if not payment_link.order:
        return

    tenant_settings = getattr(payment_link.tenant, "settings", None)
    if not tenant_settings or not tenant_settings.whatsapp_enabled:
        return
    if not getattr(tenant_settings, "notify_payment_failed", True):
        return

    from django.conf import settings as django_settings

    if not getattr(django_settings, "CELERY_BROKER_URL", ""):
        return

    try:
        from apps.integrations.whatsapp.tasks import send_payment_failed_whatsapp

        send_payment_failed_whatsapp.apply_async(
            args=[str(payment_link.order.id)],
            expires=300,
            ignore_result=True,
        )
    except Exception:
        logger.exception("Falha ao agendar WhatsApp pagamento falhou")


# ============================================================
# LISTA DE LINKS
# ============================================================


@login_required
def payment_link_list(request):
    links = (
        PaymentLink.objects.filter(tenant=request.tenant)
        .select_related("order", "created_by")
        .order_by("-created_at")
    )

    status_filter = request.GET.get("status", "")
    if status_filter:
        links = links.filter(status=status_filter)

    return render(
        request,
        "payments/payment_link_list.html",
        {
            "links": links[:100],
            "status_filter": status_filter,
            "status_choices": PaymentLink.Status.choices,
        },
    )


# ============================================================
# CRIAR LINK PARA PEDIDO (AJAX)
# ============================================================


@login_required
@require_POST
def create_link_for_order(request, order_id):
    order = get_object_or_404(
        Order.objects.for_tenant(request.tenant),
        id=order_id,
    )

    settings = getattr(request.tenant, "settings", None)
    if not settings or not settings.pagarme_enabled or not settings.pagarme_api_key:
        return JsonResponse(
            {"success": False, "error": "Pagar.me não está configurado."}, status=400
        )

    try:
        installments = int(request.POST.get("installments", 1))
        if installments < 1 or installments > settings.pagarme_max_installments:
            installments = 1
    except (ValueError, TypeError):
        installments = 1

    try:
        payment_link = create_payment_link_for_order(
            order=order,
            installments=installments,
            created_by=request.user,
        )

        # CORREÇÃO CRÍTICA DE RACE CONDITION:
        # Usa on_commit para garantir que o link foi salvo no banco antes de o Celery tentar acessá-lo.
        transaction.on_commit(lambda: _send_payment_link_whatsapp(payment_link))

        return JsonResponse(
            {
                "success": True,
                "link_id": str(payment_link.id),
                "checkout_url": payment_link.checkout_url,
                "amount": str(payment_link.amount),
                "installments": payment_link.installments,
            }
        )

    except PagarmeError as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)

    except Exception:
        logger.exception("Erro inesperado ao criar link")
        return JsonResponse({"success": False, "error": "Erro interno."}, status=500)


# ============================================================
# CRIAR LINK AVULSO
# ============================================================


@login_required
def create_standalone_link(request):
    settings = getattr(request.tenant, "settings", None)
    if not settings or not settings.pagarme_enabled or not settings.pagarme_api_key:
        messages.error(request, "Pagar.me não está configurado.")
        return redirect("payment_link_list")

    if request.method == "POST":
        description = request.POST.get("description", "").strip()
        amount_str = request.POST.get("amount", "").replace(".", "").replace(",", ".")
        customer_name = request.POST.get("customer_name", "").strip()
        customer_phone = request.POST.get("customer_phone", "").strip()
        customer_email = request.POST.get("customer_email", "").strip()

        try:
            installments = int(request.POST.get("installments", 1))
            if installments < 1 or installments > settings.pagarme_max_installments:
                installments = 1
        except (ValueError, TypeError):
            installments = 1

        errors = []
        if not description:
            errors.append("Descrição é obrigatória")
        if not customer_name:
            errors.append("Nome do cliente é obrigatório")

        try:
            amount = Decimal(amount_str)
            if amount <= 0:
                errors.append("Valor deve ser maior que zero")
        except (InvalidOperation, ValueError):
            errors.append("Valor inválido")
            amount = None

        if errors:
            for error in errors:
                messages.error(request, error)
            return render(
                request,
                "payments/create_standalone.html",
                {
                    "form_data": request.POST,
                    "max_installments": settings.pagarme_max_installments,
                },
            )

        try:
            payment_link = create_standalone_payment_link(
                tenant=request.tenant,
                amount=amount,
                description=description,
                customer_name=customer_name,
                customer_phone=customer_phone,
                customer_email=customer_email,
                installments=installments,
                created_by=request.user,
            )

            messages.success(request, "Link criado com sucesso!")
            return redirect("payment_link_detail", link_id=payment_link.id)

        except PagarmeError as e:
            messages.error(request, f"Erro Pagar.me: {e}")
        except Exception:
            logger.exception("Erro ao criar link avulso")
            messages.error(request, "Erro interno.")

    return render(
        request,
        "payments/create_standalone.html",
        {
            "max_installments": settings.pagarme_max_installments,
        },
    )


# ============================================================
# DETALHES DO LINK
# ============================================================


@login_required
def payment_link_detail(request, link_id):
    link = get_object_or_404(
        PaymentLink.objects.filter(tenant=request.tenant),
        id=link_id,
    )
    return render(request, "payments/payment_link_detail.html", {"link": link})


# ============================================================
# WEBHOOK PAGAR.ME
# ============================================================


@csrf_exempt
@require_POST
def pagarme_webhook(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
        event_type = payload.get("type", "")
        data = payload.get("data", {})

        logger.info("Webhook Pagar.me recebido: %s", event_type)

        pagarme_link_code = _extract_pagarme_link_code(event_type, data)
        charge_id = data.get("id") if event_type.startswith("charge") else None
        order_id = (data.get("order") or {}).get("id")

        if not pagarme_link_code:
            return HttpResponse("OK", status=200)

        payment_link = PaymentLink.objects.filter(
            pagarme_order_id=pagarme_link_code
        ).first()

        if not payment_link:
            logger.warning(
                "PaymentLink não encontrado: pl=%s ch=%s or=%s",
                pagarme_link_code,
                charge_id,
                order_id,
            )
            return HttpResponse("OK", status=200)

        # =====================
        # SEGURANÇA: ASSINATURA
        # =====================
        settings = getattr(payment_link.tenant, "settings", None)
        if settings and settings.pagarme_api_key:
            if not _is_valid_pagarme_signature(request, settings.pagarme_api_key):
                logger.warning(
                    "Webhook Pagar.me: Assinatura inválida para Link: %s",
                    payment_link.id,
                )
                return HttpResponse("Forbidden", status=403)

        if charge_id and not payment_link.pagarme_charge_id:
            payment_link.pagarme_charge_id = charge_id
            payment_link.save(update_fields=["pagarme_charge_id"])

        # =====================
        # STATUS
        # =====================

        if event_type in ("charge.paid", "order.paid", "paymentlink.paid"):
            if payment_link.status != PaymentLink.Status.PAID:
                # Chama método do model que salva os dados do Payer
                # O model agora usa OrderStatusService que já dispara a notificação
                payment_link.mark_as_paid(webhook_data=payload)

        elif event_type == "payment-link.expired":
            if payment_link.status == PaymentLink.Status.PENDING:
                payment_link.status = PaymentLink.Status.EXPIRED
                payment_link.webhook_data = payload
                payment_link.save(update_fields=["status", "webhook_data"])

        elif event_type == "charge.payment_failed":
            payment_link.mark_as_failed(webhook_data=payload)
            transaction.on_commit(lambda: _send_payment_failed_whatsapp(payment_link))

        elif event_type in ("paymentlink.canceled", "order.canceled"):
            payment_link.status = PaymentLink.Status.CANCELED
            payment_link.webhook_data = payload
            payment_link.save(update_fields=["status", "webhook_data"])

        elif event_type == "charge.refunded":
            payment_link.status = PaymentLink.Status.REFUNDED
            payment_link.webhook_data = payload
            payment_link.save(update_fields=["status", "webhook_data"])

        return HttpResponse("OK", status=200)

    except json.JSONDecodeError:
        logger.error("Webhook Pagar.me: JSON inválido")
        return HttpResponse("Invalid JSON", status=400)

    except Exception:
        logger.exception("Erro no webhook Pagar.me")
        return HttpResponse("Error", status=500)
