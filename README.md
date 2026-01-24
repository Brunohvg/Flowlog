# 🚀 Flowlog

**Flowlog** é uma plataforma robusta de gestão de vendas e logística para e-commerce, projetada para empresas que precisam de agilidade, automação via WhatsApp e controle multi-tenant (múltiplas lojas/unidades).

![Dashboard Preview](docs/images/dashboard_preview.png)

## ✨ Principais Funcionalidades

- 🏗️ **Multi-tenant Robust**: Isolamento total de dados entre diferentes lojas na mesma instância.
- 📦 **Gestão de Pedidos**: Fluxo completo desde a criação até a entrega final (Ready-to-Ship, Pickup, Delivery).
- 📱 **Automação WhatsApp**: Notificações automáticas de status via Evolution API utilizando snapshots de dados para evitar inconsistências.
- 💳 **Checkout Integrado**: Geração de links de pagamento profissionais via Pagar.me API v5.
- 📊 **Dashboard Analytics**: Visão em tempo real de faturamento, funil de vendas e performance logística.
- 🧪 **Blindagem Técnica**: Suíte de testes automatizados cobrindo fluxos financeiros e de segurança.

## 🛠️ Stack Tecnológica

- **Backend**: Django 5.2 (LTS) & Django REST Framework
- **Database**: PostgreSQL (Produção) / SQLite (Dev)
- **Task Queue**: Celery & Redis
- **Infra**: Docker & Docker Swarm (Pronto para escala)
- **Gerenciador de Pacotes**: `uv` (Performance extrema)

## 🚀 Início Rápido

### Pré-requisitos
- [uv](https://github.com/astral-sh/uv) instalado.
- Docker (opcional, para serviços como Redis/Postgres).

### Instalação (Local)

```bash
# 1. Clonar e entrar no diretório
git clone https://github.com/vidal/flowlog.git && cd flowlog

# 2. Instalar dependências e criar virtualenv
uv sync

# 3. Configurar variáveis de ambiente
cp .env.example .env

# 4. Rodar migrações e criar admin
uv run manage.py migrate
uv run manage.py createsuperuser

# 5. Iniciar o servidor de desenvolvimento
uv run manage.py runserver
```

## 📚 Documentação Técnica

Consulte os guias detalhados para aprofundar seu conhecimento no sistema:

- [🏗️ Arquitetura](./docs/ARCHITECTURE.md): Detalhes sobre models, multi-tenancy e fluxos assíncronos.
- [🔌 API REST](./docs/API.md): Documentação dos endpoints e integração externa.
- [🛠️ Desenvolvimento](./docs/DEVELOP.md): Comandos úteis, padrões de código e como rodar testes.
- [🚀 Deploy](./docs/DEPLOY.md): Passo a passo para colocar em produção via Docker Swarm.

## 🧪 Testes

Para garantir a qualidade e o faturamento das lojas:

```bash
# Rodar todos os testes
uv run pytest

# Gerar relatório de cobertura
uv run coverage run -m pytest
uv run coverage report
```

---

## 📄 Licença

Proprietário - Todos os direitos reservados.
