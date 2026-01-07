# 📦 Flowlog - Documentação Completa

> Sistema de Gestão de Pedidos com Integração WhatsApp

**Versão:** 11.0  
**Última atualização:** Janeiro 2026  
**Desenvolvido para:** Loja Bibelo

---

## 📑 Índice

1. [Visão Geral](#1-visão-geral)
2. [Arquitetura](#2-arquitetura)
3. [Instalação](#3-instalação)
4. [Configuração](#4-configuração)
5. [Funcionalidades](#5-funcionalidades)
6. [Fluxo de Pedidos](#6-fluxo-de-pedidos)
7. [Integração WhatsApp](#7-integração-whatsapp)
8. [API e Modelos](#8-api-e-modelos)
9. [Deploy em Produção](#9-deploy-em-produção)
10. [Troubleshooting](#10-troubleshooting)
11. [Roadmap](#11-roadmap)

---

## 1. Visão Geral

### O que é o Flowlog?

Flowlog é um sistema SaaS multi-tenant para gestão de pedidos de vendas realizadas via WhatsApp ou telefone. Desenvolvido para empresas que fazem vendas manuais e precisam de:

- Controle centralizado de pedidos
- Rastreamento de entregas
- Notificações automáticas via WhatsApp
- Relatórios de vendas
- Portal de rastreio para clientes

### Principais Características

| Característica | Descrição |
|----------------|-----------|
| **Multi-tenant** | Cada empresa tem seus dados isolados |
| **4 Tipos de Entrega** | Retirada, Motoboy, SEDEX, PAC |
| **WhatsApp Automático** | Notificações em cada etapa do pedido |
| **Rastreio Público** | Cliente consulta status sem login |
| **Código de Retirada** | 4 dígitos para retiradas na loja |
| **Relatórios** | Dashboard com métricas e gráficos |

### Tecnologias

- **Backend:** Django 5.1 + Python 3.12
- **Banco de Dados:** PostgreSQL 16 (produção) / SQLite (dev)
- **Fila de Tarefas:** Celery + Redis
- **WhatsApp:** Evolution API
- **Frontend:** Django Templates + Tailwind CSS
- **Deploy:** Docker Swarm + Traefik

---

## 2. Arquitetura

### Estrutura de Diretórios

```
Flowlog/
├── apps/                       # Aplicações Django
│   ├── accounts/               # Autenticação e usuários
│   │   ├── models.py           # User customizado
│   │   └── templates/auth/     # Tela de login
│   │
│   ├── core/                   # Funcionalidades compartilhadas
│   │   ├── middleware.py       # TenantMiddleware
│   │   ├── managers.py         # TenantManager
│   │   ├── models.py           # TenantModel base
│   │   ├── views.py            # Dashboard, Relatórios, Settings
│   │   └── templatetags/       # Filtros customizados
│   │
│   ├── orders/                 # Gestão de pedidos
│   │   ├── models.py           # Order, Customer, OrderHistory
│   │   ├── views.py            # CRUD de pedidos
│   │   ├── services.py         # Lógica de negócio (OrderStatusService)
│   │   ├── forms.py            # Formulários
│   │   ├── tracking_views.py   # Portal de rastreio público
│   │   └── templates/orders/   # Templates de pedidos
│   │
│   ├── tenants/                # Multi-tenancy
│   │   ├── models.py           # Tenant, TenantSettings
│   │   └── admin.py            # Admin do Django
│   │
│   └── integrations/           # Integrações externas
│       └── whatsapp/
│           ├── client.py       # EvolutionAPIClient
│           ├── services.py     # WhatsAppNotificationService
│           ├── tasks.py        # Celery tasks
│           └── views.py        # Setup do WhatsApp
│
├── config/                     # Configurações Django
│   ├── settings.py             # Settings principal
│   ├── urls.py                 # URLs raiz
│   └── celery.py               # Configuração Celery
│
├── templates/                  # Templates globais
│   ├── base/                   # Layout base
│   ├── dashboard/              # Dashboard
│   ├── reports/                # Relatórios
│   ├── settings/               # Configurações
│   ├── tracking/               # Rastreio público
│   └── customers/              # Gestão de clientes
│
├── static/                     # Arquivos estáticos
├── docs/                       # Documentação
├── Dockerfile                  # Imagem Docker
├── docker-compose.yml          # Stack completa
├── requirements.txt            # Dependências Python
└── manage.py                   # CLI Django
```

### Diagrama de Componentes

```
┌─────────────────────────────────────────────────────────────────┐
│                         FLOWLOG                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐  │
│  │  Django  │───▶│PostgreSQL│    │  Redis   │◀───│  Celery  │  │
│  │   App    │    │    DB    │    │  Broker  │    │  Worker  │  │
│  └────┬─────┘    └──────────┘    └──────────┘    └────┬─────┘  │
│       │                                               │         │
│       │              ┌──────────────┐                │         │
│       └─────────────▶│ Evolution API│◀───────────────┘         │
│                      │  (WhatsApp)  │                           │
│                      └──────────────┘                           │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│  Traefik (Reverse Proxy + SSL)                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Multi-Tenancy

O sistema usa **tenant por usuário**. Cada usuário pertence a um Tenant (empresa):

```python
# Middleware injeta tenant em cada request
class TenantMiddleware:
    def __call__(self, request):
        if request.user.is_authenticated:
            request.tenant = request.user.tenant
```

```python
# Models herdam de TenantModel para filtro automático
class Order(TenantModel):
    # Queries são automaticamente filtradas por tenant
    objects = TenantManager()
```

---

## 3. Instalação

### Requisitos

- Python 3.12+
- PostgreSQL 16+ (produção) ou SQLite (dev)
- Redis 7+ (para Celery)
- Docker + Docker Compose (recomendado)

### Desenvolvimento Local

```bash
# 1. Clonar repositório
git clone <repo> && cd Flowlog

# 2. Criar ambiente virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# 3. Instalar dependências
pip install -r requirements.txt

# 4. Configurar ambiente
cp .env.example .env
# Editar .env com DEBUG=True e USE_SQLITE=True

# 5. Criar banco e migrações
python manage.py migrate

# 6. Criar superusuário
python manage.py createsuperuser

# 7. Rodar servidor
python manage.py runserver
```

### Com Docker (Recomendado)

```bash
# 1. Configurar ambiente
cp .env.example .env
# Editar .env

# 2. Subir containers
docker-compose up -d

# 3. Criar migrações
docker-compose exec web python manage.py migrate

# 4. Criar superusuário
docker-compose exec web python manage.py createsuperuser
```

---

## 4. Configuração

### Variáveis de Ambiente

#### Desenvolvimento (.env.local)

```env
# Geral
SECRET_KEY=dev-secret-key-qualquer-coisa
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
SITE_URL=http://localhost:8000

# Banco - SQLite local
USE_SQLITE=True

# WhatsApp (Evolution API)
EVOLUTION_API_URL=https://api.lojabibelo.com.br
EVOLUTION_API_KEY=sua-api-key

# Celery (opcional em dev)
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
```

#### Produção (.env.producao)

```env
# Geral
SECRET_KEY=chave-super-secreta-mude-isso
DEBUG=False
ALLOWED_HOSTS=flowlog.seudominio.com.br
CSRF_TRUSTED_ORIGINS=https://flowlog.seudominio.com.br
SITE_URL=https://flowlog.seudominio.com.br

# Banco - PostgreSQL
USE_SQLITE=False
DB_NAME=flowlog
DB_USER=flowlog
DB_PASSWORD=senha-forte
DB_HOST=postgres
DB_PORT=5432

# WhatsApp
EVOLUTION_API_URL=https://api.seudominio.com.br
EVOLUTION_API_KEY=sua-api-key

# Celery + Redis
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/1
```

### Configurações por Tenant (TenantSettings)

Cada empresa pode configurar:

| Campo | Descrição |
|-------|-----------|
| `evolution_instance` | Nome da instância WhatsApp |
| `evolution_instance_token` | Token da instância |
| `pickup_expiry_hours` | Horas para expirar retirada (padrão: 72) |
| `msg_order_created` | Mensagem: pedido criado |
| `msg_order_confirmed` | Mensagem: pedido confirmado |
| `msg_order_ready_for_pickup` | Mensagem: pronto para retirada |
| `msg_order_shipped` | Mensagem: pedido enviado |
| `msg_order_delivered` | Mensagem: pedido entregue |
| `msg_order_cancelled` | Mensagem: pedido cancelado |
| `notify_order_created` | Ativar notificação: criação |
| `notify_order_confirmed` | Ativar notificação: confirmação |
| ... | (12 toggles no total) |

### Variáveis nas Mensagens

As mensagens WhatsApp suportam variáveis:

| Variável | Descrição |
|----------|-----------|
| `{cliente}` | Nome do cliente |
| `{codigo}` | Código do pedido (PED-XXXXX) |
| `{valor}` | Valor total formatado |
| `{rastreio}` | Código de rastreio |
| `{link}` | Link de rastreamento |
| `{codigo_retirada}` | Código 4 dígitos (retirada) |
| `{data_expiracao}` | Data limite para retirada |

**Exemplo de mensagem:**
```
Olá {cliente}! 👋

Seu pedido {codigo} no valor de R$ {valor} foi confirmado!

Acompanhe: {link}
```

---

## 5. Funcionalidades

### 5.1 Dashboard

**URL:** `/dashboard/`

Exibe:
- **KPIs:** Receita total, pedidos hoje
- **Funil:** Pendentes → Preparação → Trânsito → Concluídos
- **Alertas:** Falhas de entrega, retiradas expirando, pedidos prioritários
- **Gráficos:** Vendas por período, por tipo de entrega, por pagamento
- **Transações Recentes:** Últimos 10 pedidos

### 5.2 Gestão de Pedidos

**URL:** `/orders/`

#### Criar Pedido
- Cliente (nome, telefone, CPF)
- Valor total
- Tipo de entrega (Retirada/Motoboy/SEDEX/PAC)
- Endereço (se entrega)
- Status de pagamento
- Observações
- Prioridade (urgente)

#### Status do Pedido

**Order Status (status do pedido):**
| Status | Descrição |
|--------|-----------|
| `pending` | Aguardando confirmação |
| `confirmed` | Confirmado |
| `completed` | Finalizado |
| `cancelled` | Cancelado |
| `returned` | Devolvido/Reembolsado |

**Delivery Status (status da entrega):**
| Status | Descrição |
|--------|-----------|
| `pending` | Aguardando |
| `ready_for_pickup` | Pronto para retirada |
| `shipped` | Enviado |
| `delivered` | Entregue |
| `picked_up` | Retirado |
| `failed_attempt` | Falha na entrega |
| `expired` | Expirado (retirada não feita) |

#### Ações Disponíveis

| Ação | Descrição | Quando usar |
|------|-----------|-------------|
| **Confirmar** | Confirma o pedido | Após verificar pagamento |
| **Enviar** | Marca como enviado | Ao despachar (pede código rastreio) |
| **Marcar Pronto** | Pronto para retirada | Pedido de retirada preparado |
| **Marcar Entregue** | Finaliza entrega | Cliente recebeu |
| **Marcar Retirado** | Finaliza retirada | Cliente retirou na loja |
| **Cancelar** | Cancela pedido | Com ou sem reembolso |
| **Devolver** | Devolução/reembolso | Após entrega, cliente devolveu |
| **Alterar Entrega** | Muda tipo de entrega | Cliente mudou preferência |

### 5.3 Clientes

**URL:** `/customers/`

- Lista de clientes cadastrados
- Histórico de pedidos por cliente
- Edição de dados (nome, telefone, CPF, endereço)
- Total gasto pelo cliente

### 5.4 Relatórios

**URL:** `/reports/`

Filtros:
- Período (hoje, 7 dias, 30 dias, personalizado)
- Status do pedido
- Tipo de entrega
- Status de pagamento

Métricas:
- Total de vendas (R$)
- Ticket médio
- Quantidade de pedidos
- Pedidos por tipo de entrega
- Pagos vs Pendentes

### 5.5 Configurações

**URL:** `/settings/`

- **Dados da Empresa:** Nome, informações
- **Mensagens WhatsApp:** Personalizar cada mensagem
- **Notificações:** Ativar/desativar cada tipo
- **WhatsApp Setup:** Conectar instância Evolution API

### 5.6 Rastreio Público

**URLs:**
- `/rastreio/` - Busca por CPF
- `/rastreio/{codigo}/` - Detalhes do pedido (público)
- `/r/{codigo}/` - Link curto

O cliente pode:
- Consultar status sem login
- Ver timeline do pedido
- Ver código de retirada (se aplicável)
- Ver código de rastreio (se enviado)

### 5.7 Etiquetas

**URL:** `/orders/{id}/label/`

Gera etiqueta para impressão com:
- Código do pedido
- Tipo de entrega (com cor)
- Dados do cliente
- Valor e status de pagamento
- Código de retirada (se aplicável)
- Código de rastreio (se enviado)
- QR Code

Tamanhos: 1/4 A4 ou 10x10cm

---

## 6. Fluxo de Pedidos

### 6.1 Fluxo de Retirada na Loja

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   CRIADO    │────▶│  CONFIRMADO │────▶│   PRONTO    │────▶│  RETIRADO   │
│             │     │             │     │  RETIRADA   │     │             │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
      │                   │                   │                    │
      ▼                   ▼                   ▼                    ▼
 WhatsApp:           WhatsApp:           WhatsApp:            WhatsApp:
 "Pedido criado"     "Confirmado"        "Pronto! Código:     "Retirado!"
                                          1234. Válido até
                                          XX/XX"

                                               │
                                               ▼ (se não retirar)
                                         ┌─────────────┐
                                         │  EXPIRADO   │
                                         └─────────────┘
                                               │
                                               ▼
                                          WhatsApp:
                                          "Pedido expirou"
```

### 6.2 Fluxo de Entrega (Motoboy/SEDEX/PAC)

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   CRIADO    │────▶│  CONFIRMADO │────▶│   ENVIADO   │────▶│   ENTREGUE  │
│             │     │             │     │             │     │             │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
      │                   │                   │                    │
      ▼                   ▼                   ▼                    ▼
 WhatsApp:           WhatsApp:           WhatsApp:            WhatsApp:
 "Pedido criado"     "Confirmado"        "Enviado!            "Entregue!"
                                          Rastreio: XX123"

                                               │
                                               ▼ (se falhar)
                                         ┌─────────────┐
                                         │   FALHA     │
                                         │   ENTREGA   │
                                         └─────────────┘
                                               │
                                               ▼
                                          WhatsApp:
                                          "Tentativa falhou"
```

### 6.3 Fluxo de Cancelamento

```
┌─────────────┐                    ┌─────────────┐
│  QUALQUER   │───(Cancelar)──────▶│  CANCELADO  │
│   STATUS    │                    │             │
└─────────────┘                    └─────────────┘
                                         │
                                         ▼
                                    WhatsApp:
                                    "Pedido cancelado"
                                    (com ou sem reembolso)
```

### 6.4 Fluxo de Devolução

```
┌─────────────┐                    ┌─────────────┐
│   ENTREGUE  │───(Devolver)──────▶│  DEVOLVIDO  │
│  RETIRADO   │                    │             │
└─────────────┘                    └─────────────┘
                                         │
                                         ▼
                                    WhatsApp:
                                    "Devolução processada"
```

---

## 7. Integração WhatsApp

### 7.1 Evolution API

O Flowlog usa a **Evolution API** para enviar mensagens WhatsApp. É necessário ter uma instância da Evolution API rodando.

**Documentação:** https://doc.evolution-api.com/

### 7.2 Configuração

1. Acesse `/settings/whatsapp/`
2. Digite um nome para a instância (ex: `loja-bibelo`)
3. Clique em "Criar Instância"
4. Escaneie o QR Code com WhatsApp
5. Aguarde conexão

### 7.3 Estrutura do Client

```python
# apps/integrations/whatsapp/client.py

class EvolutionAPIClient:
    """Cliente para Evolution API."""
    
    def send_text(self, to: str, message: str) -> dict:
        """Envia mensagem de texto."""
        
    def instance_exists(self, instance_name: str) -> bool:
        """Verifica se instância existe."""
        
    def create_instance(self, instance_name: str) -> dict:
        """Cria nova instância."""
        
    def get_qr_code(self, instance_name: str) -> str:
        """Retorna QR code em base64."""
        
    def get_connection_state(self, instance_name: str) -> str:
        """Retorna estado da conexão."""
```

### 7.4 Celery Tasks

As notificações são enviadas de forma assíncrona via Celery:

```python
# apps/integrations/whatsapp/tasks.py

@shared_task
def send_order_created_whatsapp(order_id: str):
    """Notifica cliente sobre novo pedido."""

@shared_task
def send_order_confirmed_whatsapp(order_id: str):
    """Notifica confirmação do pedido."""

@shared_task
def send_order_ready_for_pickup_whatsapp(order_id: str):
    """Notifica que está pronto para retirada."""

@shared_task
def send_order_shipped_whatsapp(order_id: str):
    """Notifica envio com código de rastreio."""

# ... outras tasks
```

### 7.5 Controle Granular

Cada notificação pode ser ativada/desativada individualmente:

| Evento | Campo | Padrão |
|--------|-------|--------|
| Pedido criado | `notify_order_created` | ✅ |
| Pedido confirmado | `notify_order_confirmed` | ✅ |
| Pronto para retirada | `notify_ready_for_pickup` | ✅ |
| Pedido enviado | `notify_order_shipped` | ✅ |
| Pedido entregue | `notify_order_delivered` | ✅ |
| Pedido retirado | `notify_order_picked_up` | ✅ |
| Pedido cancelado | `notify_order_cancelled` | ✅ |
| Pedido devolvido | `notify_order_returned` | ✅ |
| Falha na entrega | `notify_delivery_failed` | ✅ |
| Retirada expirando | `notify_pickup_expiring` | ✅ |
| Retirada expirada | `notify_pickup_expired` | ✅ |
| Pagamento recebido | `notify_payment_received` | ✅ |

---

## 8. API e Modelos

### 8.1 Modelos Principais

#### Tenant (Empresa)

```python
class Tenant(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
```

#### User (Usuário)

```python
class User(AbstractUser):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    role = models.CharField(choices=[('admin', 'Admin'), ('seller', 'Vendedor')])
    phone = models.CharField(max_length=20, blank=True)
```

#### Customer (Cliente)

```python
class Customer(TenantModel):
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20)
    cpf = models.CharField(max_length=14, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
```

#### Order (Pedido)

```python
class Order(TenantModel):
    code = models.CharField(max_length=20, unique=True)  # PED-XXXXX
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT)
    total_value = models.DecimalField(max_digits=10, decimal_places=2)
    
    order_status = models.CharField(choices=OrderStatus.choices)
    delivery_status = models.CharField(choices=DeliveryStatus.choices)
    payment_status = models.CharField(choices=PaymentStatus.choices)
    
    delivery_type = models.CharField(choices=DeliveryType.choices)
    delivery_address = models.TextField(blank=True)
    tracking_code = models.CharField(max_length=50, blank=True)
    
    pickup_code = models.CharField(max_length=4, blank=True)  # Código 4 dígitos
    expires_at = models.DateTimeField(null=True)  # Expiração retirada
    
    is_priority = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL)
```

#### OrderHistory (Histórico)

```python
class OrderHistory(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    action = models.CharField(max_length=50)  # created, confirmed, shipped, etc.
    description = models.TextField()
    old_status = models.CharField(max_length=50, blank=True)
    new_status = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL)
```

### 8.2 Enums de Status

```python
class OrderStatus(models.TextChoices):
    PENDING = 'pending', 'Pendente'
    CONFIRMED = 'confirmed', 'Confirmado'
    COMPLETED = 'completed', 'Concluído'
    CANCELLED = 'cancelled', 'Cancelado'
    RETURNED = 'returned', 'Devolvido'

class DeliveryStatus(models.TextChoices):
    PENDING = 'pending', 'Pendente'
    READY_FOR_PICKUP = 'ready_for_pickup', 'Pronto para Retirada'
    SHIPPED = 'shipped', 'Enviado'
    DELIVERED = 'delivered', 'Entregue'
    PICKED_UP = 'picked_up', 'Retirado'
    FAILED_ATTEMPT = 'failed_attempt', 'Falha na Entrega'
    EXPIRED = 'expired', 'Expirado'

class PaymentStatus(models.TextChoices):
    PENDING = 'pending', 'Pendente'
    PAID = 'paid', 'Pago'

class DeliveryType(models.TextChoices):
    PICKUP = 'pickup', 'Retirada na Loja'
    MOTOBOY = 'motoboy', 'Motoboy'
    SEDEX = 'sedex', 'SEDEX'
    PAC = 'pac', 'PAC'
```

### 8.3 Service Layer

A lógica de negócio está centralizada em `OrderStatusService`:

```python
# apps/orders/services.py

class OrderStatusService:
    """Serviço para transições de status de pedidos."""
    
    def confirm_order(self, order, user):
        """Confirma pedido pendente."""
        
    def ship_order(self, order, user, tracking_code):
        """Marca pedido como enviado."""
        
    def mark_ready_for_pickup(self, order, user):
        """Marca pronto para retirada (gera código 4 dígitos)."""
        
    def mark_delivered(self, order, user):
        """Marca como entregue."""
        
    def mark_picked_up(self, order, user):
        """Marca como retirado."""
        
    def cancel_order(self, order, user, reason, refunded):
        """Cancela pedido."""
        
    def return_order(self, order, user, reason):
        """Processa devolução."""
        
    def change_delivery_type(self, order, user, new_type, address):
        """Altera tipo de entrega."""
```

---

## 9. Deploy em Produção

### 9.1 Pré-requisitos

- Servidor Linux (Ubuntu 22.04+ recomendado)
- Docker + Docker Swarm
- Domínio configurado
- SSL (via Traefik/Let's Encrypt)

### 9.2 Docker Compose (docker-compose.yml)

```yaml
version: '3.8'

services:
  web:
    image: ghcr.io/seuusuario/flowlog:v11
    environment:
      - DEBUG=False
    env_file:
      - .env
    depends_on:
      - postgres
      - redis
    deploy:
      replicas: 2
      labels:
        - "traefik.enable=true"
        - "traefik.http.routers.flowlog.rule=Host(`flowlog.seudominio.com.br`)"

  celery:
    image: ghcr.io/seuusuario/flowlog:v11
    command: celery -A config worker -l INFO
    env_file:
      - .env
    depends_on:
      - redis

  celery-beat:
    image: ghcr.io/seuusuario/flowlog:v11
    command: celery -A config beat -l INFO
    env_file:
      - .env
    depends_on:
      - redis

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: flowlog
      POSTGRES_USER: flowlog
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data

volumes:
  postgres_data:
  redis_data:
```

### 9.3 Comandos de Deploy

```bash
# 1. Build da imagem
./deploy.sh
# Digite a versão: v11

# 2. No servidor, atualizar stack
docker stack deploy -c docker-compose.yml flowlog

# 3. Executar migrations
docker exec -it $(docker ps -q -f name=flowlog_web) python manage.py migrate

# 4. Coletar arquivos estáticos
docker exec -it $(docker ps -q -f name=flowlog_web) python manage.py collectstatic --noinput
```

### 9.4 Checklist de Produção

- [ ] `DEBUG=False`
- [ ] `SECRET_KEY` única e segura
- [ ] `ALLOWED_HOSTS` configurado
- [ ] `CSRF_TRUSTED_ORIGINS` configurado
- [ ] SSL/HTTPS ativo
- [ ] Backup do banco configurado
- [ ] Monitoramento (logs, uptime)
- [ ] Redis protegido (não exposto)
- [ ] PostgreSQL protegido (não exposto)

---

## 10. Troubleshooting

### Problema: Pedidos lentos ao salvar (local)

**Causa:** Tentando conectar no Redis que não está rodando.

**Solução:** Com `DEBUG=True`, as notificações são automaticamente puladas.

### Problema: WhatsApp não conecta

**Verificar:**
1. Evolution API está rodando?
2. URL e API Key estão corretos?
3. Instância foi criada?
4. QR Code foi escaneado?

**Comandos:**
```bash
# Testar conexão com Evolution API
curl -X GET "https://api.seudominio.com.br/instance/fetchInstances" \
  -H "apikey: SUA_API_KEY"
```

### Problema: Mensagens não estão sendo enviadas

**Verificar:**
1. Celery worker está rodando?
2. Redis está rodando?
3. Notificação está ativada nas configurações?
4. Instância WhatsApp está conectada?

**Comandos:**
```bash
# Ver logs do Celery
docker logs -f $(docker ps -q -f name=celery)

# Verificar fila do Redis
redis-cli LLEN celery
```

### Problema: Migration falhou

**Solução:**
```bash
# Ver estado das migrations
python manage.py showmigrations

# Forçar migration específica
python manage.py migrate tenants 0004_granular_notifications

# Criar migration vazia para corrigir
python manage.py makemigrations --empty tenants
```

### Problema: Erro 500 em produção

**Verificar:**
```bash
# Ver logs do container
docker logs -f $(docker ps -q -f name=flowlog_web)

# Verificar settings
python manage.py check --deploy
```

---

## 11. Roadmap

### v12 - Busca e Exportação
- [ ] Busca avançada (nome, telefone, código, data)
- [ ] Exportar relatórios em PDF
- [ ] Exportar relatórios em Excel

### v13 - Rastreio Automático
- [ ] Integração API Correios
- [ ] Atualização automática de status
- [ ] Webhook para tracking

### v14 - Multi-vendedor
- [ ] Cada vendedor vê só seus pedidos
- [ ] Dashboard por vendedor
- [ ] Comissões por venda

### v15 - API REST
- [ ] Endpoints públicos
- [ ] Autenticação JWT
- [ ] Documentação Swagger

### Futuro
- [ ] PWA Mobile
- [ ] Chatbot WhatsApp
- [ ] Cálculo automático de frete
- [ ] Controle de estoque
- [ ] Modo escuro

---

## 📞 Suporte

**Desenvolvido por:** Claude (Anthropic)  
**Para:** Bruno Henrique / Loja Bibelo  
**Versão:** 11.0  
**Data:** Janeiro 2026

---

*Esta documentação é gerada automaticamente e pode ser atualizada conforme novas funcionalidades são implementadas.*
