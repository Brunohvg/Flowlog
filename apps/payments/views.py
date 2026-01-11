"""
Views do app payments - Links de Pagamento
"""

import json
import logging
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.orders.models import Order
from apps.payments.models import PaymentLink
from apps.payments.services import (
    create_payment_link_for_order,
    create_standalone_payment_link,
    PagarmeError,
)

logger = logging.getLogger(__name__)


def _send_payment_link_whatsapp(payment_link):
    """
    Envia link de pagamento via WhatsApp.
    Mesma lógica do orders/services.py:
    - Se CELERY_BROKER_URL não configurado: ignora silenciosamente
    - Se Redis indisponível: loga erro mas não trava
    """
    if not payment_link.order:
        return
    
    from django.conf import settings as django_settings
    
    # Se não tem broker configurado, não faz nada
    broker_url = getattr(django_settings, 'CELERY_BROKER_URL', '')
    if not broker_url:
        return
    
    # Tenta enviar via Celery
    try:
        from apps.integrations.whatsapp.tasks import send_payment_link_whatsapp
        send_payment_link_whatsapp.apply_async(
            args=[str(payment_link.order.id), str(payment_link.id)],
            expires=300,
            ignore_result=True,
        )
    except Exception as e:
        logger.error("Falha ao agendar WhatsApp link pagamento: %s", str(e))


# ============================================================
# LISTA DE LINKS
# ============================================================

@login_required
def payment_link_list(request):
    """Lista todos os links de pagamento"""
    links = PaymentLink.objects.filter(
        tenant=request.tenant
    ).select_related("order", "created_by").order_by("-created_at")
    
    # Filtros
    status_filter = request.GET.get("status", "")
    if status_filter:
        links = links.filter(status=status_filter)
    
    context = {
        "links": links[:100],  # Limita a 100
        "status_filter": status_filter,
        "status_choices": PaymentLink.Status.choices,
    }
    return render(request, "payments/payment_link_list.html", context)


# ============================================================
# CRIAR LINK DO PEDIDO (AJAX)
# ============================================================

@login_required
@require_POST
def create_link_for_order(request, order_id):
    """Cria link de pagamento para um pedido (AJAX)"""
    
    order = get_object_or_404(
        Order.objects.for_tenant(request.tenant),
        id=order_id
    )
    
    # Verifica se Pagar.me está configurado
    settings = getattr(request.tenant, "settings", None)
    if not settings or not settings.pagarme_enabled or not settings.pagarme_api_key:
        return JsonResponse({
            "success": False,
            "error": "Pagar.me não está configurado. Vá em Configurações → Pagar.me"
        }, status=400)
    
    # Pega parcelas do POST
    try:
        installments = int(request.POST.get("installments", 1))
        if installments < 1 or installments > settings.pagarme_max_installments:
            installments = 1
    except (ValueError, TypeError):
        installments = 1
    
    try:
        # Cria o link
        payment_link = create_payment_link_for_order(
            order=order,
            installments=installments,
            created_by=request.user,
        )
        
        # Envia WhatsApp com o link (se configurado)
        _send_payment_link_whatsapp(payment_link)
        
        return JsonResponse({
            "success": True,
            "link_id": str(payment_link.id),
            "checkout_url": payment_link.checkout_url,
            "amount": str(payment_link.amount),
            "installments": payment_link.installments,
        })
        
    except PagarmeError as e:
        logger.error("Erro ao criar link Pagar.me: %s", str(e))
        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=400)
    except Exception as e:
        logger.exception("Erro inesperado ao criar link")
        return JsonResponse({
            "success": False,
            "error": "Erro interno. Tente novamente."
        }, status=500)


# ============================================================
# CRIAR LINK AVULSO
# ============================================================

@login_required
def create_standalone_link(request):
    """Página para criar link avulso"""
    
    # Verifica se Pagar.me está configurado
    settings = getattr(request.tenant, "settings", None)
    if not settings or not settings.pagarme_enabled or not settings.pagarme_api_key:
        messages.error(request, "Pagar.me não está configurado. Vá em Configurações → Pagar.me")
        return redirect("payment_link_list")
    
    if request.method == "POST":
        # Pega dados do form
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
        
        # Validações
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
            return render(request, "payments/create_standalone.html", {
                "form_data": request.POST,
                "max_installments": settings.pagarme_max_installments,
            })
        
        try:
            # Cria o link
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
            
            messages.success(request, f"Link criado com sucesso!")
            return redirect("payment_link_detail", link_id=payment_link.id)
            
        except PagarmeError as e:
            messages.error(request, f"Erro Pagar.me: {str(e)}")
        except Exception as e:
            logger.exception("Erro ao criar link avulso")
            messages.error(request, "Erro interno. Tente novamente.")
    
    return render(request, "payments/create_standalone.html", {
        "max_installments": settings.pagarme_max_installments,
    })


# ============================================================
# DETALHES DO LINK
# ============================================================

@login_required
def payment_link_detail(request, link_id):
    """Detalhes de um link de pagamento"""
    
    link = get_object_or_404(
        PaymentLink.objects.filter(tenant=request.tenant),
        id=link_id
    )
    
    return render(request, "payments/payment_link_detail.html", {"link": link})


# ============================================================
# WEBHOOK PAGAR.ME
# ============================================================

@csrf_exempt
@require_POST
def pagarme_webhook(request):
    """
    Recebe webhooks do Pagar.me
    
    Eventos tratados (Payment Links):
    - paymentlink.paid: Link pago
    - paymentlink.canceled: Link cancelado
    - order.paid: Pedido do link pago
    - order.canceled: Pedido cancelado
    - charge.paid: Cobrança paga
    - charge.payment_failed: Pagamento falhou
    - charge.refunded: Estorno
    """
    
    try:
        # Parse do body
        body = request.body.decode("utf-8")
        data = json.loads(body)
        
        event_type = data.get("type", "")
        event_data = data.get("data", {})
        
        logger.info("Webhook Pagar.me recebido: %s", event_type)
        logger.debug("Webhook data: %s", body[:500])
        
        # Identifica o ID do payment link ou order
        link_id = None
        order_id = None
        charge_id = None
        
        # Para eventos de paymentlink
        if event_type.startswith("paymentlink"):
            link_id = event_data.get("id")
        # Para eventos de order (criados a partir do paymentlink)
        elif event_type.startswith("order"):
            order_id = event_data.get("id")
            # Também pode ter referência ao payment_link
            if "payment_link" in event_data:
                link_id = event_data.get("payment_link", {}).get("id")
        # Para eventos de charge
        elif event_type.startswith("charge"):
            charge_id = event_data.get("id")
            # Busca order_id da charge
            if "order" in event_data:
                order_id = event_data.get("order", {}).get("id")
        
        # Busca o PaymentLink por diferentes campos
        payment_link = None
        
        # Primeiro tenta pelo ID do payment link (pl_xxx)
        if link_id:
            payment_link = PaymentLink.objects.filter(
                pagarme_order_id=link_id
            ).first()
        
        # Se não encontrou, tenta pelo order_id
        if not payment_link and order_id:
            payment_link = PaymentLink.objects.filter(
                pagarme_order_id=order_id
            ).first()
        
        # Se ainda não encontrou, tenta pelo charge_id
        if not payment_link and charge_id:
            payment_link = PaymentLink.objects.filter(
                pagarme_charge_id=charge_id
            ).first()
        
        if not payment_link:
            logger.warning(
                "PaymentLink não encontrado para webhook: link_id=%s, order_id=%s, charge_id=%s", 
                link_id, order_id, charge_id
            )
            # Retorna 200 para não reenviar o webhook
            return HttpResponse("OK", status=200)
        
        # Processa evento
        if event_type in ["paymentlink.paid", "order.paid", "charge.paid"]:
            if payment_link.status != PaymentLink.Status.PAID:
                payment_link.mark_as_paid(webhook_data=data)
                logger.info("PaymentLink %s marcado como PAGO", payment_link.id)
                
                # Envia WhatsApp se configurado
                _send_payment_confirmation_whatsapp(payment_link)
            
        elif event_type in ["charge.payment_failed"]:
            payment_link.mark_as_failed(webhook_data=data)
            logger.info("PaymentLink %s marcado como FALHOU", payment_link.id)
            
            # Envia WhatsApp de pagamento falho
            _send_payment_failed_whatsapp(payment_link)
            
        elif event_type in ["paymentlink.canceled", "order.canceled"]:
            payment_link.status = PaymentLink.Status.CANCELED
            payment_link.webhook_data = data
            payment_link.save()
            logger.info("PaymentLink %s marcado como CANCELADO", payment_link.id)
            
        elif event_type in ["charge.refunded"]:
            payment_link.status = PaymentLink.Status.REFUNDED
            payment_link.webhook_data = data
            payment_link.save()
            logger.info("PaymentLink %s marcado como ESTORNADO", payment_link.id)
        
        return HttpResponse("OK", status=200)
        
    except json.JSONDecodeError:
        logger.error("Webhook Pagar.me: JSON inválido")
        return HttpResponse("Invalid JSON", status=400)
    except Exception as e:
        logger.exception("Erro no webhook Pagar.me: %s", str(e))
        return HttpResponse("Error", status=500)


def _send_payment_confirmation_whatsapp(payment_link):
    """
    Envia WhatsApp de confirmação de pagamento.
    Mesma lógica do orders/services.py.
    """
    if not payment_link.order:
        return
    
    # Verifica se notificação está habilitada
    tenant_settings = getattr(payment_link.tenant, "settings", None)
    if not tenant_settings or not tenant_settings.whatsapp_enabled:
        return
    if not tenant_settings.notify_payment_received:
        return
    
    from django.conf import settings as django_settings
    
    # Se não tem broker configurado, não faz nada
    broker_url = getattr(django_settings, 'CELERY_BROKER_URL', '')
    if not broker_url:
        return
    
    # Tenta enviar via Celery
    try:
        from apps.integrations.whatsapp.tasks import send_payment_received_whatsapp
        send_payment_received_whatsapp.apply_async(
            args=[str(payment_link.order.id)],
            expires=300,
            ignore_result=True,
        )
    except Exception as e:
        logger.error("Falha ao agendar WhatsApp confirmação pagamento: %s", str(e))


def _send_payment_failed_whatsapp(payment_link):
    """
    Envia WhatsApp quando pagamento falha.
    """
    if not payment_link.order:
        return
    
    # Verifica se notificação está habilitada
    tenant_settings = getattr(payment_link.tenant, "settings", None)
    if not tenant_settings or not tenant_settings.whatsapp_enabled:
        return
    if not getattr(tenant_settings, 'notify_payment_failed', True):
        return
    
    from django.conf import settings as django_settings
    
    # Se não tem broker configurado, não faz nada
    broker_url = getattr(django_settings, 'CELERY_BROKER_URL', '')
    if not broker_url:
        return
    
    # Tenta enviar via Celery
    try:
        from apps.integrations.whatsapp.tasks import send_payment_failed_whatsapp
        send_payment_failed_whatsapp.apply_async(
            args=[str(payment_link.order.id)],
            expires=300,
            ignore_result=True,
        )
    except Exception as e:
        logger.error("Falha ao agendar WhatsApp pagamento falhou: %s", str(e))
