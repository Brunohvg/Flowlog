"""
Views para integração WhatsApp - Flowlog v10.

Lógica de segurança:
- Token GLOBAL (settings.py) → Apenas para CRIAR instâncias
- Token da INSTÂNCIA (salvo no tenant) → Para todas as outras ações
  (enviar mensagem, QR code, verificar status, etc.)

Isso evita que alguém que saiba o nome de uma instância possa
enviar mensagens sem autorização.
"""

import logging
import re

from django.conf import settings as django_settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from apps.integrations.whatsapp.client import EvolutionClient, EvolutionAPIError
from apps.tenants.models import TenantSettings

logger = logging.getLogger(__name__)


def _get_global_client():
    """
    Cliente com token GLOBAL - APENAS para criar instâncias.
    """
    api_url = getattr(django_settings, 'EVOLUTION_API_URL', '')
    api_key = getattr(django_settings, 'EVOLUTION_API_KEY', '')
    
    if not api_url or not api_key:
        return None
    
    return EvolutionClient(
        base_url=api_url,
        api_key=api_key,
        instance=None,
    )


def _get_instance_client(tenant_settings):
    """
    Cliente com token da INSTÂNCIA - para todas as ações.
    Mais seguro pois cada instância tem seu próprio token.
    """
    api_url = getattr(django_settings, 'EVOLUTION_API_URL', '')
    
    if not api_url or not tenant_settings.evolution_instance or not tenant_settings.evolution_instance_token:
        return None
    
    return EvolutionClient(
        base_url=api_url,
        api_key=tenant_settings.evolution_instance_token,  # Token da instância!
        instance=tenant_settings.evolution_instance,
    )


def _is_api_configured():
    """Verifica se a API está configurada globalmente."""
    api_url = getattr(django_settings, 'EVOLUTION_API_URL', '')
    api_key = getattr(django_settings, 'EVOLUTION_API_KEY', '')
    return bool(api_url and api_key)


@login_required
def whatsapp_setup(request):
    """
    Página principal de configuração do WhatsApp.
    
    Fluxo:
    1. Se não tem instância configurada -> Mostra formulário para criar
    2. Se tem instância mas não conectada -> Mostra QR Code
    3. Se conectada -> Mostra status e opção de desconectar
    """
    tenant = request.tenant
    tenant_settings = getattr(tenant, 'settings', None)
    
    if not tenant_settings:
        tenant_settings = TenantSettings.objects.create(tenant=tenant)
    
    # Verifica se API está configurada globalmente
    api_configured = _is_api_configured()
    
    context = {
        'tenant': tenant,
        'tenant_settings': tenant_settings,
        'api_configured': api_configured,
        'status': None,
        'error': None,
    }
    
    # Se não tem API configurada, mostra aviso
    if not api_configured:
        context['error'] = 'Evolution API não configurada no sistema. Contate o administrador.'
        return render(request, 'settings/whatsapp_setup.html', context)
    
    # Se tem instância e token, verifica status
    if tenant_settings.evolution_instance and tenant_settings.evolution_instance_token:
        client = _get_instance_client(tenant_settings)
        if client:
            try:
                status = client.test_connection()
                context['status'] = status
                
                # Atualiza status no banco se mudou
                if status.get('connected') != tenant_settings.whatsapp_connected:
                    tenant_settings.whatsapp_connected = status.get('connected', False)
                    if status.get('number'):
                        tenant_settings.whatsapp_number = status['number']
                    tenant_settings.save(update_fields=['whatsapp_connected', 'whatsapp_number'])
                    
            except EvolutionAPIError as e:
                context['error'] = str(e)
    
    return render(request, 'settings/whatsapp_setup.html', context)


@login_required
@require_http_methods(["POST"])
def whatsapp_create_instance(request):
    """
    Cria uma nova instância do WhatsApp.
    
    USA TOKEN GLOBAL para criar, depois salva o token individual da instância.
    """
    if not _is_api_configured():
        return JsonResponse({
            'success': False,
            'error': 'Evolution API não configurada no sistema'
        }, status=400)
    
    tenant = request.tenant
    tenant_settings = getattr(tenant, 'settings', None)
    
    if not tenant_settings:
        tenant_settings = TenantSettings.objects.create(tenant=tenant)
    
    # Nome da instância informado pelo usuário
    instance_name = request.POST.get('instance_name', '').strip().lower()
    
    if not instance_name:
        return JsonResponse({
            'success': False,
            'error': 'Informe um nome para a instância'
        }, status=400)
    
    # Sanitiza nome (só letras, números e hífen)
    instance_name = re.sub(r'[^a-z0-9-]', '', instance_name)[:50]
    
    if len(instance_name) < 3:
        return JsonResponse({
            'success': False,
            'error': 'Nome deve ter pelo menos 3 caracteres'
        }, status=400)
    
    # Verifica se já existe outro tenant com esse nome
    existing = TenantSettings.objects.filter(
        evolution_instance=instance_name
    ).exclude(tenant=tenant).exists()
    
    if existing:
        return JsonResponse({
            'success': False,
            'error': 'Este nome de instância já está em uso por outro cliente. Escolha outro nome.'
        }, status=400)
    
    # Usa cliente GLOBAL para criar instância
    global_client = _get_global_client()
    
    # Verifica se já existe NA EVOLUTION API
    if global_client.instance_exists(instance_name):
        # SEGURANÇA: Se instância existe na API mas não está no nosso banco,
        # NÃO permite conectar (pode ser de outro sistema)
        return JsonResponse({
            'success': False,
            'error': f'O nome "{instance_name}" já está em uso. Escolha outro nome.'
        }, status=400)
    
    try:
        # Cria instância e recebe o token individual
        result = global_client.create_instance(instance_name)
        
        # O token da instância vem na resposta da criação
        instance_token = result.get('token')
        
        if not instance_token:
            logger.warning("Criação de instância não retornou token: %s", result)
            # Tenta buscar token da instância
            instance_token = global_client.get_instance_token(instance_name)
        
        if not instance_token:
            return JsonResponse({
                'success': False,
                'error': 'Instância criada mas não foi possível obter o token. Tente novamente.'
            }, status=400)
        
        # Salva no tenant
        tenant_settings.evolution_instance = instance_name
        tenant_settings.evolution_instance_token = instance_token
        tenant_settings.whatsapp_enabled = True
        tenant_settings.whatsapp_connected = False
        tenant_settings.save()
        
        logger.info(
            "Instância WhatsApp criada | tenant=%s | instance=%s | has_token=%s",
            tenant.slug, instance_name, bool(instance_token)
        )
        
        return JsonResponse({
            'success': True,
            'created': True,
            'connected': False,
            'instance': instance_name,
            'message': 'Instância criada com sucesso! Escaneie o QR Code para conectar.'
        })
        
    except EvolutionAPIError as e:
        error_msg = str(e)
        
        # Se a instância já existe (erro da API)
        if 'already' in error_msg.lower() or 'existe' in error_msg.lower() or 'exists' in error_msg.lower():
            return JsonResponse({
                'success': False,
                'error': f'A instância "{instance_name}" já existe. Escolha outro nome.'
            }, status=400)
        
        logger.error("Erro ao criar instância WhatsApp: %s", e)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
def whatsapp_get_qrcode(request):
    """
    Obtém QR code para conexão.
    USA TOKEN DA INSTÂNCIA (não o global).
    """
    tenant = request.tenant
    tenant_settings = getattr(tenant, 'settings', None)
    
    if not tenant_settings or not tenant_settings.evolution_instance:
        return JsonResponse({
            'success': False,
            'error': 'Instância não configurada'
        }, status=400)
    
    # Se não tem token da instância, tenta criar/buscar
    if not tenant_settings.evolution_instance_token:
        try:
            global_client = _get_global_client()
            if global_client:
                # Tenta buscar token existente ou criar instância
                result = global_client.ensure_instance(tenant_settings.evolution_instance)
                instance_token = result.get('token') or result.get('apikey')
                if instance_token:
                    tenant_settings.evolution_instance_token = instance_token
                    tenant_settings.save(update_fields=['evolution_instance_token'])
        except Exception as e:
            logger.error("Erro ao buscar token da instância: %s", e)
    
    # Usa cliente com token da instância
    client = _get_instance_client(tenant_settings)
    
    if not client:
        return JsonResponse({
            'success': False,
            'error': 'Token da instância não configurado'
        }, status=400)
    
    try:
        # Primeiro verifica se já está conectado
        state = client.get_connection_state()
        
        if state.get('connected'):
            # Atualiza banco
            if not tenant_settings.whatsapp_connected:
                tenant_settings.whatsapp_connected = True
                tenant_settings.whatsapp_number = state.get('number', '')
                tenant_settings.save()
            
            return JsonResponse({
                'success': True,
                'connected': True,
                'number': state.get('number', ''),
            })
        
        # Não está conectado, pega QR code
        qr_data = client.get_qrcode()
        
        return JsonResponse({
            'success': True,
            'connected': False,
            'qrcode': qr_data.get('qrcode'),
            'code': qr_data.get('code'),
            'pairingCode': qr_data.get('pairingCode'),
        })
        
    except EvolutionAPIError as e:
        error_msg = str(e)
        
        # Se já está conectada
        if 'já está conectada' in error_msg.lower() or 'already connected' in error_msg.lower():
            return JsonResponse({
                'success': True,
                'connected': True,
            })
        
        logger.error("Erro ao obter QR code: %s", e)
        return JsonResponse({
            'success': False,
            'error': error_msg
        }, status=400)


@login_required
def whatsapp_check_status(request):
    """
    Verifica status de conexão.
    USA TOKEN DA INSTÂNCIA.
    """
    tenant = request.tenant
    tenant_settings = getattr(tenant, 'settings', None)
    
    if not tenant_settings or not tenant_settings.evolution_instance:
        return JsonResponse({
            'configured': False,
            'connected': False,
        })
    
    client = _get_instance_client(tenant_settings)
    
    if not client:
        return JsonResponse({
            'configured': False,
            'connected': False,
            'error': 'Token da instância não configurado'
        })
    
    try:
        state = client.get_connection_state()
        
        # Atualiza banco se mudou
        if state.get('connected') != tenant_settings.whatsapp_connected:
            tenant_settings.whatsapp_connected = state.get('connected', False)
            if state.get('number'):
                tenant_settings.whatsapp_number = state['number']
            tenant_settings.save()
        
        return JsonResponse({
            'configured': True,
            'connected': state.get('connected', False),
            'state': state.get('state', 'unknown'),
            'number': state.get('number', ''),
        })
        
    except EvolutionAPIError as e:
        return JsonResponse({
            'configured': True,
            'connected': False,
            'error': str(e)
        })


@login_required
@require_http_methods(["POST"])
def whatsapp_disconnect(request):
    """
    Desconecta o WhatsApp (logout).
    USA TOKEN DA INSTÂNCIA.
    """
    tenant = request.tenant
    tenant_settings = getattr(tenant, 'settings', None)
    
    if not tenant_settings or not tenant_settings.evolution_instance:
        return JsonResponse({
            'success': False,
            'error': 'Instância não configurada'
        }, status=400)
    
    client = _get_instance_client(tenant_settings)
    
    if not client:
        return JsonResponse({
            'success': False,
            'error': 'Token da instância não configurado'
        }, status=400)
    
    try:
        client.logout_instance()
        
        # Atualiza banco
        tenant_settings.whatsapp_connected = False
        tenant_settings.whatsapp_number = ''
        tenant_settings.save()
        
        return JsonResponse({
            'success': True,
            'message': 'WhatsApp desconectado'
        })
        
    except EvolutionAPIError as e:
        logger.error("Erro ao desconectar WhatsApp: %s", e)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
@require_http_methods(["POST"])
def whatsapp_test_message(request):
    """
    Envia mensagem de teste.
    USA TOKEN DA INSTÂNCIA.
    """
    tenant = request.tenant
    tenant_settings = getattr(tenant, 'settings', None)
    
    if not tenant_settings or not tenant_settings.is_whatsapp_configured:
        return JsonResponse({
            'success': False,
            'error': 'WhatsApp não configurado'
        }, status=400)
    
    phone = request.POST.get('phone', '').strip()
    if not phone:
        return JsonResponse({
            'success': False,
            'error': 'Informe o número de telefone'
        }, status=400)
    
    client = _get_instance_client(tenant_settings)
    
    if not client:
        return JsonResponse({
            'success': False,
            'error': 'Token da instância não configurado'
        }, status=400)
    
    try:
        message = (
            f"🧪 *Mensagem de teste do Flowlog!*\n\n"
            f"Se você recebeu esta mensagem, a integração WhatsApp está funcionando corretamente.\n\n"
            f"_{tenant.name}_"
        )
        
        client.send_text_message(phone=phone, message=message)
        
        return JsonResponse({
            'success': True,
            'message': f'Mensagem enviada para {phone}'
        })
        
    except EvolutionAPIError as e:
        logger.error("Erro ao enviar mensagem de teste: %s", e)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


# Manter compatibilidade com views antigas
@login_required
@require_http_methods(["POST"])
def whatsapp_save_config(request):
    """Mantido para compatibilidade - redireciona para setup."""
    messages.info(request, 'Use a nova interface de configuração.')
    return redirect('whatsapp_setup')
