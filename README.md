# 🚀 Flowlog

Sistema de gestão de vendas via WhatsApp com integração de pagamentos.

## ✨ Funcionalidades

- 📦 **Gestão de Pedidos** - Criação, acompanhamento e status
- 👥 **Clientes** - Cadastro e histórico
- 💳 **Pagamentos** - Links de pagamento via Pagar.me
- 📱 **WhatsApp** - Notificações automáticas via Evolution API
- 📊 **Relatórios** - Dashboard e métricas
- 🔌 **API REST** - Integração com sistemas externos
- 🏢 **Multi-tenant** - Suporte a múltiplas empresas

## 🛠️ Stack

- **Backend:** Django 5.2, Django REST Framework
- **Database:** PostgreSQL
- **Queue:** Celery + Redis
- **WhatsApp:** Evolution API
- **Pagamentos:** Pagar.me API v5

## 🚀 Quick Start

```bash
# Clone
git clone <repo> && cd flowlog

# Instalar dependências
uv sync

# Configurar ambiente
cp .env.example .env

# Migrations
uv run manage.py migrate

# Criar superuser
uv run manage.py createsuperuser

# Rodar
uv run manage.py runserver
```

## 📚 Documentação

Ver [docs/README.md](./docs/README.md) para documentação completa:

- [Arquitetura](./docs/ARCHITECTURE.md)
- [API REST](./docs/API.md)
- [Deploy](./docs/DEPLOY.md)
- [Desenvolvimento](./docs/DEVELOP.md)

## 🔗 URLs

| URL | Descrição |
|-----|-----------|
| `/` | Dashboard |
| `/api/docs/` | Swagger (API) |
| `/admin/` | Django Admin |

## 📄 Licença

Proprietário - Todos os direitos reservados.
