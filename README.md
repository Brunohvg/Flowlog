# Flowlog - Sistema de Gestão de Vendas via WhatsApp

Sistema multi-tenant para gerenciamento de vendas com integração WhatsApp, rastreamento de pedidos e suporte a múltiplos tipos de entrega.

## 🚀 Funcionalidades

### Pedidos
- ✅ Criação de pedidos com vínculo automático de clientes
- ✅ Múltiplos tipos de entrega: Motoboy, SEDEX, PAC, Retirada na Loja
- ✅ Alteração de tipo de entrega (retirada ↔ entrega)
- ✅ Rastreamento de código dos Correios
- ✅ Marcação de tentativas de entrega falhas
- ✅ Cancelamento e devolução de pedidos
- ✅ Duplicação de pedidos
- ✅ Pedidos prioritários
- ✅ Notas internas (visíveis apenas para equipe)
- ✅ Histórico completo de atividades

### Clientes
- ✅ Cadastro automático por telefone
- ✅ CPF opcional para acompanhamento
- ✅ Bloqueio de clientes
- ✅ Histórico de pedidos por cliente
- ✅ Estatísticas: total gasto, ticket médio, etc.

### Rastreamento Público
- ✅ Página pública para cliente acompanhar pedido
- ✅ Verificação de segurança (últimos 4 dígitos do telefone/CPF)
- ✅ Busca por código do pedido ou CPF
- ✅ Timeline visual do status
- ✅ Código de rastreio dos Correios integrado

### Retirada na Loja
- ✅ Liberação para retirada com timer de 48h
- ✅ Expiração automática de pedidos não retirados
- ✅ Alertas de pedidos prestes a expirar

### Notificações WhatsApp
- ✅ Mensagem de pedido criado
- ✅ Mensagem de pedido enviado (com rastreio)
- ✅ Mensagem de pedido pronto para retirada
- ✅ Mensagem de pedido entregue
- ✅ Reenvio manual de notificações
- ✅ Mensagens personalizáveis por empresa

### Dashboard
- ✅ Estatísticas em tempo real
- ✅ Alertas de pedidos críticos
- ✅ Pedidos por tipo de entrega
- ✅ Faturamento do mês
- ✅ Top clientes

### Relatórios
- ✅ Filtro por período (7, 30, 90, 365 dias)
- ✅ Resumo por status e tipo de entrega
- ✅ Ranking de clientes
- ✅ Gráficos de vendas

## 🏗️ Arquitetura

```
Flowlog/
├── apps/
│   ├── accounts/         # Autenticação e usuários
│   ├── core/             # Models base, middleware, views principais
│   ├── integrations/     # WhatsApp (Evolution API)
│   ├── orders/           # Pedidos, clientes, rastreamento
│   └── tenants/          # Multi-tenancy
├── config/               # Configurações Django
└── templates/            # Templates HTML
```

### Tecnologias
- **Backend:** Django 5.0+
- **Banco:** PostgreSQL 16+
- **Cache/Broker:** Redis 7+
- **Tasks:** Celery 5.3+
- **Frontend:** Tailwind CSS, Lucide Icons
- **WhatsApp:** Evolution API
- **Deploy:** Docker Swarm

## 📦 Instalação

### Desenvolvimento

```bash
# Clone
git clone <repo>
cd Flowlog-master

# Ambiente virtual
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# ou: .venv\Scripts\activate  # Windows

# Dependências
pip install -r requirements.txt
# ou com uv: uv sync

# Configuração
cp .env.example .env
# Edite o .env com suas configurações

# Banco de dados
python manage.py migrate

# Superusuário
python manage.py createsuperuser

# Executar
python manage.py runserver
```

### Produção (Docker)

```bash
docker-compose up -d
```

## ⚙️ Configuração

### Variáveis de Ambiente

```env
# Django
DEBUG=False
SECRET_KEY=sua-chave-secreta
ALLOWED_HOSTS=seudominio.com

# Banco de dados
DATABASE_URL=postgres://user:pass@host:5432/flowlog

# Redis
REDIS_URL=redis://localhost:6379/0

# WhatsApp (Evolution API)
EVOLUTION_API_URL=https://sua-api.com
EVOLUTION_API_KEY=sua-api-key
EVOLUTION_INSTANCE=nome-da-instancia
```

### Celery Beat (Tarefas Agendadas)

Para expiração automática de retiradas, configure o Celery Beat:

```python
# config/celery.py
app.conf.beat_schedule = {
    'expire-pending-pickups': {
        'task': 'apps.integrations.whatsapp.tasks.expire_pending_pickups',
        'schedule': 3600.0,  # A cada hora
    },
}
```

Execute o beat:
```bash
celery -A config beat -l info
```

## 🔒 Fluxo de Status

### Entrega (Motoboy/Correios)
```
PENDING → SHIPPED → DELIVERED
                 ↘ FAILED_ATTEMPT → DELIVERED
```

### Retirada na Loja
```
PENDING → READY_FOR_PICKUP → PICKED_UP
                          ↘ EXPIRED (48h)
```

### Cancelamento/Devolução
```
(qualquer status) → CANCELLED
COMPLETED → RETURNED (+ opcional REFUNDED)
```

## 📱 API de Rastreamento

### URLs Públicas
- `/rastreio/` - Busca por código ou CPF
- `/rastreio/verificar/?code=PED-XXXXX` - Verificação de identidade
- `/rastreio/cpf/` - Busca por CPF
- `/rastreio/<codigo>/` - Detalhes do pedido

### Segurança
- Verificação por últimos 4 dígitos do telefone ou CPF
- Sessão armazena pedidos verificados
- Sem exposição de dados sensíveis

## 🧪 Testes

```bash
python manage.py test
```

## 📄 Licença

Proprietário - Todos os direitos reservados.

## 🤝 Suporte

Para suporte, entre em contato pelo WhatsApp ou e-mail.
