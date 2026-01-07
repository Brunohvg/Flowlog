# 📦 Flowlog - Documentação Completa

> Sistema de Gestão de Pedidos via WhatsApp

**Versão:** 11.0  
**Última atualização:** Janeiro 2026  
**Desenvolvido para:** Operações de venda manual via WhatsApp

---

## 📑 Índice

1. [Visão Geral](#1-visão-geral)
2. [Arquitetura](#2-arquitetura)
3. [Instalação](#3-instalação)
4. [Configuração](#4-configuração)
5. [Funcionalidades](#5-funcionalidades)
6. [Fluxo de Pedidos](#6-fluxo-de-pedidos)
7. [Integrações](#7-integrações)
8. [Multi-Tenancy](#8-multi-tenancy)
9. [Segurança](#9-segurança)
10. [Troubleshooting](#10-troubleshooting)
11. [API de Referência](#11-api-de-referência)

---

## 1. Visão Geral

### 1.1 O que é o Flowlog?

Flowlog é um sistema SaaS multi-tenant para gestão de pedidos de empresas que realizam vendas manuais via WhatsApp ou telefone. O foco é na **simplicidade operacional** e **automação de comunicação** com clientes.

### 1.2 Público-Alvo

- Pequenas e médias empresas com vendas via WhatsApp
- Operações com múltiplos vendedores
- Negócios que precisam de rastreamento de pedidos
- Empresas com entregas próprias (motoboy) ou Correios

### 1.3 Principais Características

| Característica | Descrição |
|----------------|-----------|
| **Multi-Tenant** | Múltiplas empresas no mesmo sistema |
| **WhatsApp Integrado** | Notificações automáticas via Evolution API |
| **4 Tipos de Entrega** | Retirada, Motoboy, SEDEX, PAC |
| **Rastreamento Público** | Clientes acompanham pedidos sem login |
| **Controle Granular** | 12 tipos de notificação configuráveis |
| **Relatórios** | Dashboard e relatórios de vendas |

### 1.4 O que NÃO é o Flowlog

- ❌ Sistema de estoque/inventário
- ❌ E-commerce com carrinho
- ❌ Gateway de pagamento
- ❌ ERP completo

---

## 2. Arquitetura

### 2.1 Stack Tecnológico

```
┌─────────────────────────────────────────────────────┐
│                    FRONTEND                          │
│  Django Templates + Tailwind CSS + Lucide Icons     │
└─────────────────────────────────────────────────────┘
                         │
┌─────────────────────────────────────────────────────┐
│                    BACKEND                           │
│              Django 5.x + Python 3.12               │
└─────────────────────────────────────────────────────┘
                         │
        ┌────────────────┼────────────────┐
        ▼                ▼                ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  PostgreSQL  │ │    Redis     │ │ Evolution API│
│   (Dados)    │ │   (Filas)    │ │  (WhatsApp)  │
└──────────────┘ └──────────────┘ └──────────────┘
```

### 2.2 Estrutura de Diretórios

```
Flowlog/
├── apps/
│   ├── accounts/        # Autenticação e usuários
│   ├── core/            # Views principais, middleware
│   ├── integrations/    # WhatsApp (Evolution API)
│   ├── orders/          # Pedidos, clientes, entregas
│   └── tenants/         # Multi-tenancy, configurações
├── config/
│   ├── settings.py      # Configurações Django
│   ├── urls.py          # Rotas principais
│   └── celery.py        # Configuração de tarefas
├── templates/           # Templates globais
├── static/              # Arquivos estáticos
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

### 2.3 Modelo de Dados

```
┌─────────────┐       ┌─────────────┐       ┌─────────────┐
│   Tenant    │───┬───│    User     │       │  Customer   │
│  (Empresa)  │   │   │ (Vendedor)  │       │  (Cliente)  │
└─────────────┘   │   └─────────────┘       └──────┬──────┘
       │          │                                 │
       │    ┌─────┴─────┐                          │
       │    │           │                          │
       ▼    ▼           ▼                          ▼
┌─────────────┐   ┌─────────────┐         ┌─────────────┐
│  Settings   │   │    Order    │◄────────│   Order     │
│  (Config)   │   │  (Pedido)   │         │  History    │
└─────────────┘   └──────┬──────┘         └─────────────┘
                         │
                         ▼
                  ┌─────────────┐
                  │  Delivery   │
                  │   Status    │
                  └─────────────┘
```

### 2.4 Apps e Responsabilidades

| App | Responsabilidade |
|-----|------------------|
| `accounts` | Autenticação, modelo User customizado |
| `core` | Dashboard, relatórios, middleware tenant |
| `orders` | CRUD pedidos, clientes, status, etiquetas |
| `tenants` | Modelo Tenant, TenantSettings |
| `integrations` | Evolution API client, tasks Celery |

---

## 3. Instalação

### 3.1 Requisitos

- Python 3.12+
- PostgreSQL 15+ (produção) ou SQLite (desenvolvimento)
- Redis 7+ (para Celery)
- Docker + Docker Compose (recomendado)
- Evolution API (para WhatsApp)

### 3.2 Desenvolvimento Local

```bash
# 1. Clonar repositório
git clone <repo> && cd Flowlog

# 2. Criar ambiente virtual
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# 3. Instalar dependências
pip install -r requirements.txt

# 4. Configurar ambiente
cp .env.example .env
# Editar .env com suas configurações

# 5. Criar banco e migrações
python manage.py migrate

# 6. Criar superusuário
python manage.py createsuperuser

# 7. Rodar servidor
python manage.py runserver
```

### 3.3 Produção com Docker

```bash
# 1. Configurar .env
cp .env.example .env
# Editar com valores de produção

# 2. Build da imagem
./deploy.sh
# Digite a versão: v11

# 3. Deploy no Swarm
docker stack deploy -c docker-compose.yml flowlog

# 4. Migrations
docker exec -it <container> python manage.py migrate
```

### 3.4 Variáveis de Ambiente

| Variável | Descrição | Exemplo |
|----------|-----------|---------|
| `SECRET_KEY` | Chave secreta Django | `super-secret-key` |
| `DEBUG` | Modo debug | `False` |
| `ALLOWED_HOSTS` | Hosts permitidos | `flowlog.exemplo.com` |
| `USE_SQLITE` | Usar SQLite | `False` |
| `DB_NAME` | Nome do banco | `flowlog` |
| `DB_USER` | Usuário do banco | `flowlog` |
| `DB_PASSWORD` | Senha do banco | `senha123` |
| `DB_HOST` | Host do banco | `postgres` |
| `DB_PORT` | Porta do banco | `5432` |
| `EVOLUTION_API_URL` | URL da Evolution API | `https://api.exemplo.com` |
| `EVOLUTION_API_KEY` | Chave global da API | `sua-chave` |
| `CELERY_BROKER_URL` | URL do Redis | `redis://redis:6379/0` |
| `SITE_URL` | URL pública do site | `https://flowlog.exemplo.com` |

---

## 4. Configuração

### 4.1 Primeiro Acesso

1. Acesse `/admin` com o superusuário
2. Crie um **Tenant** (empresa)
3. Crie um **User** vinculado ao tenant (role: `admin`)
4. Faça logout e acesse com o novo usuário

### 4.2 Configurações do Tenant

Acesse **Configurações** no menu lateral:

#### Informações da Empresa
- Nome da empresa
- Telefone de contato
- Prazo de retirada (dias)

#### WhatsApp (Evolution API)
- Nome da instância
- Conexão via QR Code
- Status da conexão

#### Notificações Granulares (12 toggles)

| Categoria | Notificações |
|-----------|--------------|
| **Pedido** | Criado, Confirmado, Cancelado |
| **Pagamento** | Confirmado |
| **Entrega** | Enviado, Saiu para Entrega, Entregue, Falha |
| **Retirada** | Pronto, Retirado, Expirando, Expirado |

#### Mensagens Personalizadas
Cada notificação tem uma mensagem customizável com variáveis:

```
Variáveis disponíveis:
{codigo}        - Código do pedido (PED-XXXXX)
{cliente}       - Nome do cliente
{valor}         - Valor total
{rastreio}      - Código de rastreio
{link_rastreio} - Link público de rastreamento
{pickup_code}   - Código de retirada (4 dígitos)
{dias_restantes}- Dias para retirar
{empresa}       - Nome da empresa
```

---

## 5. Funcionalidades

### 5.1 Dashboard

**Métricas Principais:**
- Receita total (apenas pedidos pagos e não cancelados)
- Pedidos hoje
- Pipeline visual (Aguardando → Preparação → Trânsito → Concluído)

**Alertas:**
- 🔴 Falhas na entrega
- 🟡 Retiradas expirando
- 🔴 Pedidos prioritários

**Transações Recentes:**
- Últimos 5 pedidos com status visual

### 5.2 Pedidos

#### Criar Pedido
1. Selecionar ou criar cliente (CPF único por tenant)
2. Informar valor total
3. Escolher tipo de entrega
4. Marcar como pago (opcional)
5. Marcar como prioritário (opcional)
6. Adicionar observações

#### Status do Pedido (`order_status`)
| Status | Descrição |
|--------|-----------|
| `pending` | Aguardando confirmação |
| `confirmed` | Confirmado, em preparação |
| `completed` | Finalizado com sucesso |
| `cancelled` | Cancelado |
| `returned` | Devolvido/Reembolsado |

#### Status de Entrega (`delivery_status`)
| Status | Descrição |
|--------|-----------|
| `pending` | Aguardando envio |
| `ready_for_pickup` | Pronto para retirada |
| `shipped` | Enviado |
| `out_for_delivery` | Saiu para entrega |
| `delivered` | Entregue |
| `picked_up` | Retirado |
| `failed_attempt` | Tentativa falhou |
| `expired` | Prazo expirado |

#### Ações Disponíveis
- ✏️ Editar pedido
- 📦 Marcar como enviado
- ✅ Confirmar entrega/retirada
- 💰 Confirmar pagamento
- ❌ Cancelar pedido
- ↩️ Registrar devolução
- 🏷️ Imprimir etiqueta
- 🔄 Alterar tipo de entrega

### 5.3 Clientes

- Cadastro com CPF único (por tenant)
- Nome, telefone, endereço
- Histórico de pedidos
- Total gasto

### 5.4 Relatórios

**Filtros:**
- Período (hoje, 7 dias, 30 dias, custom)
- Tipo de entrega
- Status de pagamento

**Métricas:**
- Total de pedidos
- Receita (só pagos não cancelados)
- Ticket médio
- Gráfico de vendas por dia
- Distribuição por tipo de entrega
- Status de pagamento

### 5.5 Rastreamento Público

**URL:** `/rastrear/`

Clientes podem:
1. Buscar por CPF (ver todos os pedidos)
2. Buscar por código do pedido
3. Ver timeline de status
4. Ver código de retirada (quando aplicável)

**Não requer login!**

### 5.6 Etiquetas

Dois tamanhos disponíveis:
- **1/4 A4** (105mm x 148mm)
- **Compacta** (100mm x 100mm)

Informações na etiqueta:
- Código do pedido
- Tipo de entrega (cor diferente)
- Cliente e telefone
- Valor e status de pagamento
- Endereço (se entrega)
- Código de retirada + QR (se retirada)
- Código de rastreio (se Correios)
- Data e empresa

---

## 6. Fluxo de Pedidos

### 6.1 Retirada na Loja

```
┌─────────┐    ┌───────────┐    ┌─────────────┐    ┌──────────┐
│ CRIADO  │───▶│ CONFIRMADO│───▶│PRONTO RETIRA│───▶│ RETIRADO │
└─────────┘    └───────────┘    └─────────────┘    └──────────┘
     │                               │
     │                               ▼
     │                        ┌─────────────┐
     └───────────────────────▶│  EXPIRADO   │
                              └─────────────┘
```

**Código de Retirada:** 4 dígitos gerados automaticamente  
**Prazo:** Configurável (padrão 7 dias)

### 6.2 Motoboy

```
┌─────────┐    ┌───────────┐    ┌─────────┐    ┌──────────┐
│ CRIADO  │───▶│ CONFIRMADO│───▶│ ENVIADO │───▶│ ENTREGUE │
└─────────┘    └───────────┘    └─────────┘    └──────────┘
                                     │
                                     ▼
                              ┌─────────────┐
                              │FALHA ENTREGA│
                              └─────────────┘
```

### 6.3 Correios (SEDEX/PAC)

```
┌─────────┐    ┌───────────┐    ┌─────────┐    ┌──────────┐
│ CRIADO  │───▶│ CONFIRMADO│───▶│ ENVIADO │───▶│ ENTREGUE │
└─────────┘    └───────────┘    └─────────┘    └──────────┘
                                     │
                                     │ (código rastreio obrigatório)
                                     ▼
                          Link: 17track.net/pt/track
```

### 6.4 Cancelamento e Devolução

```
QUALQUER STATUS ───▶ CANCELADO (sem reembolso)
                 └──▶ DEVOLVIDO (com reembolso)
```

**Regra de Negócio:** Pedidos cancelados/devolvidos:
- Não contam na receita
- Mostram badge "Reembolsado" se estavam pagos
- Status visual diferenciado (vermelho/laranja)

---

## 7. Integrações

### 7.1 Evolution API (WhatsApp)

#### Configuração
1. Ter Evolution API instalada
2. Configurar `EVOLUTION_API_URL` e `EVOLUTION_API_KEY` no .env
3. Em **Configurações > WhatsApp**, criar instância
4. Escanear QR Code com WhatsApp

#### Endpoints Utilizados

| Endpoint | Uso |
|----------|-----|
| `POST /instance/create` | Criar instância |
| `GET /instance/connect/{name}` | Gerar QR Code |
| `GET /instance/connectionState/{name}` | Verificar conexão |
| `POST /message/sendText/{name}` | Enviar mensagem |
| `DELETE /instance/delete/{name}` | Remover instância |

#### Segurança
- Cada tenant tem sua própria instância
- Não é permitido conectar a instâncias existentes de outros
- Token da instância armazenado por tenant

### 7.2 Celery (Tarefas Assíncronas)

**Tasks disponíveis:**

| Task | Trigger | Descrição |
|------|---------|-----------|
| `send_order_created_whatsapp` | Criar pedido | Notifica cliente |
| `send_order_confirmed_whatsapp` | Confirmar pedido | Notifica cliente |
| `send_payment_confirmed_whatsapp` | Confirmar pagamento | Notifica cliente |
| `send_order_shipped_whatsapp` | Marcar enviado | Notifica cliente |
| `send_order_delivered_whatsapp` | Confirmar entrega | Notifica cliente |
| `send_order_ready_for_pickup_whatsapp` | Pronto retirada | Notifica cliente |
| `send_pickup_reminder_whatsapp` | Cron diário | Lembra retiradas pendentes |
| `expire_pending_pickups` | Cron diário | Expira retiradas vencidas |

**Configuração Cron (Celery Beat):**
```python
# Executar diariamente às 9h
expire_pending_pickups
send_pickup_reminders
```

---

## 8. Multi-Tenancy

### 8.1 Modelo de Isolamento

- **Banco compartilhado** com coluna `tenant_id`
- **Filtro automático** via middleware
- **Sem acesso cruzado** entre tenants

### 8.2 Middleware

```python
# apps/core/middleware.py
class TenantMiddleware:
    def __call__(self, request):
        if request.user.is_authenticated:
            request.tenant = request.user.tenant
        else:
            request.tenant = None
        return self.get_response(request)
```

### 8.3 Queries Seguras

```python
# Sempre filtrar por tenant
orders = Order.objects.filter(tenant=request.tenant)

# Manager customizado (automático)
class TenantManager(models.Manager):
    def for_tenant(self, tenant):
        return self.filter(tenant=tenant)
```

### 8.4 Roles

| Role | Permissões |
|------|------------|
| `admin` | Tudo: configurações, usuários, pedidos |
| `seller` | Apenas pedidos e clientes |

---

## 9. Segurança

### 9.1 Proteções Implementadas

| Proteção | Implementação |
|----------|---------------|
| **CSRF** | Token em todos os forms POST |
| **XSS** | Escape automático Django |
| **SQL Injection** | ORM Django |
| **Tenant Isolation** | Middleware + filtros |
| **Senhas** | Hash bcrypt |
| **Sessões** | Cookie seguro (HTTPS) |

### 9.2 Configurações de Produção

```python
# settings.py (produção)
DEBUG = False
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
```

### 9.3 Vulnerabilidades Corrigidas (v11)

| Vulnerabilidade | Correção |
|-----------------|----------|
| WhatsApp Instance Hijack | Bloqueia conectar a instância existente |
| Redis Timeout | Skip notificações quando DEBUG=True |

---

## 10. Troubleshooting

### 10.1 Problemas Comuns

#### Pedidos lentos para salvar (local)
**Causa:** Tentando conectar no Redis sem ele rodando  
**Solução:** Usar `DEBUG=True` no .env (skip automático)

#### WhatsApp não conecta
**Causa:** Instância já existe ou API offline  
**Solução:** 
1. Verificar se Evolution API está rodando
2. Escolher nome de instância único
3. Verificar logs: `docker logs flowlog_celery`

#### Etiqueta não imprime
**Causa:** CSS de impressão incorreto  
**Solução:** Atualizar para v11 (corrigido)

#### Status incorreto na listagem
**Causa:** Faltava tratar `order_status == 'returned'`  
**Solução:** Atualizar para v11 (corrigido)

### 10.2 Logs

```bash
# Logs do container web
docker logs flowlog_web -f

# Logs do Celery
docker logs flowlog_celery -f

# Logs do Django (se DEBUG=True)
# Aparecem no console
```

### 10.3 Reset de Dados (Desenvolvimento)

```bash
# Apagar banco e recriar
rm db.sqlite3
python manage.py migrate
python manage.py createsuperuser
```

---

## 11. API de Referência

### 11.1 URLs Principais

| URL | View | Descrição |
|-----|------|-----------|
| `/` | `DashboardView` | Dashboard |
| `/pedidos/` | `order_list` | Lista de pedidos |
| `/pedidos/novo/` | `order_create` | Criar pedido |
| `/pedidos/<id>/` | `order_detail` | Detalhe do pedido |
| `/clientes/` | `customer_list` | Lista de clientes |
| `/relatorios/` | `ReportsView` | Relatórios |
| `/configuracoes/` | `settings_view` | Configurações |
| `/rastrear/` | `tracking_search` | Rastreamento público |

### 11.2 URLs de Ações

| URL | Método | Descrição |
|-----|--------|-----------|
| `/pedidos/<id>/confirmar/` | POST | Confirmar pedido |
| `/pedidos/<id>/enviar/` | POST | Marcar como enviado |
| `/pedidos/<id>/entregar/` | POST | Confirmar entrega |
| `/pedidos/<id>/cancelar/` | POST | Cancelar pedido |
| `/pedidos/<id>/devolver/` | POST | Registrar devolução |
| `/pedidos/<id>/pagar/` | POST | Confirmar pagamento |

### 11.3 URLs WhatsApp (AJAX)

| URL | Método | Descrição |
|-----|--------|-----------|
| `/integrations/whatsapp/status/` | GET | Status da conexão |
| `/integrations/whatsapp/create-instance/` | POST | Criar instância |
| `/integrations/whatsapp/qrcode/` | GET | Obter QR Code |
| `/integrations/whatsapp/disconnect/` | POST | Desconectar |

---

## 📝 Changelog

### v11 (Janeiro 2026)
- ✅ Notificações granulares (12 toggles)
- ✅ Correção de status Devolvido/Reembolsado
- ✅ Correção etiqueta de impressão
- ✅ Alerta de pedidos prioritários
- ✅ Segurança: bloqueio de instância WhatsApp existente
- ✅ Performance: skip Redis quando DEBUG=True

### v10
- ✅ Etiquetas com dois tamanhos
- ✅ Código de retirada 4 dígitos
- ✅ Timeline de rastreamento

### v9
- ✅ Evolution API integration
- ✅ Multi-tenancy completo
- ✅ Dashboard com gráficos

---

## 📞 Suporte

Para dúvidas ou problemas:
1. Verificar esta documentação
2. Consultar logs do sistema
3. Abrir issue no repositório

---

*Documentação gerada em Janeiro 2026*
