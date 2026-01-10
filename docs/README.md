# 📚 Flowlog - Documentação

Sistema de gestão de vendas via WhatsApp com integração Pagar.me.

## 📑 Índice

| Documento | Descrição |
|-----------|-----------|
| [ARCHITECTURE.md](./ARCHITECTURE.md) | Arquitetura e estrutura do projeto |
| [API.md](./API.md) | Documentação da API REST |
| [DEPLOY.md](./DEPLOY.md) | Guia de deploy em produção |
| [DEVELOP.md](./DEVELOP.md) | Guia de desenvolvimento local |
| [ROADMAP.md](./ROADMAP.md) | Roadmap e funcionalidades futuras |

## 🚀 Quick Start

```bash
# Clone
git clone <repo> && cd flowlog

# Instalar dependências
uv sync

# Configurar ambiente
cp .env.example .env
# Editar .env com suas credenciais

# Migrations
uv run manage.py migrate

# Criar superuser
uv run manage.py createsuperuser

# Rodar
uv run manage.py runserver
```

## 🔗 URLs Principais

| URL | Descrição |
|-----|-----------|
| `/` | Dashboard |
| `/api/docs/` | Documentação Swagger da API |
| `/api/v1/` | API REST v1 |
| `/admin/` | Django Admin |
| `/pedidos/` | Gestão de pedidos |
| `/clientes/` | Gestão de clientes |
| `/configuracoes/` | Configurações do sistema |

## 📦 Apps

```
apps/
├── accounts/      # Usuários e autenticação
├── api/           # API REST
│   └── v1/        # Versão 1
├── core/          # Dashboard, relatórios, configurações
├── integrations/  # WhatsApp (Evolution API)
├── orders/        # Pedidos e clientes
├── payments/      # Links de pagamento (Pagar.me)
└── tenants/       # Multi-tenancy
```

## 🔧 Integrações

- **Evolution API** - WhatsApp Business
- **Pagar.me** - Links de pagamento

## 📄 Licença

Proprietário - Todos os direitos reservados.
