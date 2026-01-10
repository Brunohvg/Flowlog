# 🏗️ Flowlog - Arquitetura

## 📁 Estrutura do Projeto

```
flowlog/
├── apps/                      # Aplicações Django
│   ├── __init__.py
│   ├── accounts/              # Usuários e autenticação
│   │   ├── models.py          # CustomUser, TenantUser
│   │   ├── admin.py
│   │   └── ...
│   │
│   ├── api/                   # API REST
│   │   ├── urls.py            # Router principal
│   │   └── v1/                # Versão 1
│   │       ├── serializers.py # Serializers DRF
│   │       ├── views.py       # ViewSets
│   │       └── urls.py        # Rotas v1
│   │
│   ├── core/                  # Funcionalidades centrais
│   │   ├── views.py           # Dashboard, relatórios, configurações
│   │   ├── urls.py
│   │   └── templates/         # Templates específicos
│   │
│   ├── integrations/          # Integrações externas
│   │   └── whatsapp/          # Evolution API
│   │       ├── client.py      # Cliente HTTP
│   │       ├── services.py    # Lógica de notificações
│   │       ├── tasks.py       # Tasks Celery
│   │       └── urls.py
│   │
│   ├── orders/                # Pedidos e clientes
│   │   ├── models.py          # Order, Customer, OrderActivity
│   │   ├── services.py        # OrderService, OrderStatusService
│   │   ├── views.py           # CRUD de pedidos
│   │   ├── customer_views.py  # CRUD de clientes
│   │   ├── tracking_views.py  # Rastreio público
│   │   └── templates/
│   │
│   ├── payments/              # Pagamentos
│   │   ├── models.py          # PaymentLink
│   │   ├── services.py        # PagarmeService
│   │   ├── views.py           # CRUD + webhook
│   │   └── templates/
│   │
│   └── tenants/               # Multi-tenancy
│       ├── models.py          # Tenant, TenantSettings
│       ├── middleware.py      # TenantMiddleware
│       └── mixins.py          # TenantMixin, TenantModel
│
├── config/                    # Configurações Django
│   ├── __init__.py
│   ├── settings.py            # Settings principal
│   ├── urls.py                # URLs raiz
│   ├── celery.py              # Configuração Celery
│   ├── wsgi.py
│   └── asgi.py
│
├── docs/                      # Documentação
│   ├── README.md              # Índice
│   ├── API.md                 # API REST
│   ├── ARCHITECTURE.md        # Este arquivo
│   ├── DEPLOY.md              # Deploy
│   └── DEVELOP.md             # Desenvolvimento
│
├── static/                    # Arquivos estáticos
├── templates/                 # Templates globais
│   ├── base/                  # Base templates
│   ├── dashboard/
│   ├── orders/
│   ├── payments/
│   └── settings/
│
├── manage.py
├── pyproject.toml             # Dependências (uv)
├── requirements.txt           # Gerado por uv
├── Dockerfile
├── docker-compose.yml
└── deploy.sh
```

## 🧩 Apps e Responsabilidades

### accounts
- Modelo de usuário customizado
- Relação usuário-tenant

### api
- API REST com DRF
- Versionamento (/v1/, /v2/, etc)
- Documentação Swagger

### core
- Dashboard com métricas
- Relatórios
- Configurações gerais
- Perfil do usuário

### integrations
- **whatsapp**: Notificações via Evolution API
- Estrutura pronta para novas integrações

### orders
- CRUD de pedidos
- CRUD de clientes
- Rastreio público
- Status e ciclo de vida do pedido

### payments
- Integração Pagar.me
- Links de pagamento
- Webhooks de confirmação

### tenants
- Isolamento de dados por tenant
- Configurações específicas por tenant
- Middleware de tenant

## 🔄 Fluxos Principais

### Criação de Pedido
```
1. View recebe dados
2. OrderService.create_order()
3. Cria/busca Customer
4. Cria Order
5. Se WhatsApp habilitado: agenda notificação via Celery
```

### Link de Pagamento
```
1. View recebe pedido + parcelas
2. PagarmeService.create_payment_link()
3. Salva PaymentLink no banco
4. Se WhatsApp habilitado: envia link ao cliente
5. Cliente paga no checkout Pagar.me
6. Webhook recebe confirmação
7. Atualiza PaymentLink e Order
8. Envia notificação de pagamento
```

### Notificação WhatsApp
```
1. Evento dispara (pedido criado, pago, etc)
2. Verifica CELERY_BROKER_URL
3. Se configurado: task.apply_async()
4. Celery worker executa
5. WhatsAppNotificationService envia
6. NotificationLog registra resultado
```

## 🔒 Multi-tenancy

O sistema usa **filtro por tenant** em todas as queries:

```python
# middleware.py
request.tenant = Tenant.objects.get(domain=request.get_host())

# models.py
class TenantModel(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    
    class Meta:
        abstract = True

# views.py
Order.objects.for_tenant(request.tenant)
```

## ⚙️ Variáveis de Ambiente

| Variável | Descrição | Default |
|----------|-----------|---------|
| `DEBUG` | Debug mode | False |
| `SECRET_KEY` | Chave secreta | (obrigatório) |
| `DATABASE_URL` | URL PostgreSQL | sqlite |
| `ALLOWED_HOSTS` | Hosts permitidos | localhost |
| `CELERY_BROKER_URL` | URL Redis | "" (desabilitado) |
| `EVOLUTION_API_URL` | URL Evolution API | "" |
| `SITE_URL` | URL pública do sistema | localhost:8000 |

## 🐳 Docker

```yaml
services:
  web:           # Django + Gunicorn
  celery:        # Worker Celery
  celerybeat:    # Scheduler
  postgres:      # Banco de dados
  redis:         # Broker Celery
```

## 📊 Banco de Dados

### Principais Tabelas
- `tenants_tenant` - Tenants
- `tenants_tenantsettings` - Configurações
- `orders_customer` - Clientes
- `orders_order` - Pedidos
- `payments_paymentlink` - Links de pagamento
- `integrations_notificationlog` - Logs de notificação
