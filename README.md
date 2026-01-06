# 📦 Flowlog - Sistema de Gestão de Pedidos (SaaS)

![Status](https://img.shields.io/badge/Status-Em%20Desenvolvimento-blue)
![Python](https://img.shields.io/badge/Python-3.11+-yellow)
![Django](https://img.shields.io/badge/Django-5.0+-green)
![Docker](https://img.shields.io/badge/Docker-Ready-blue)

O **Flowlog** é um sistema robusto de gestão de pedidos e logística (OMS) focado em pequenas operações e e-commerce. Construído com Django, oferece um painel administrativo moderno, integração com WhatsApp e relatórios financeiros detalhados.

## 🚀 Funcionalidades Principais

* **Dashboard Executivo:** Métricas em tempo real com gráficos interativos (ApexCharts).
* **Gestão de Pedidos:** Fluxo completo (Pendente -> Processamento -> Enviado -> Entregue).
* **Funil de Vendas:** Visualização gráfica do pipeline de pedidos.
* **Integração WhatsApp:** Notificações automáticas de status via Evolution API.
* **Relatórios Financeiros:** Análise de receita, ticket médio e performance logística.
* **Multi-Tenant:** Arquitetura preparada para múltiplas lojas (SaaS).
* **Design Premium:** Interface limpa e responsiva com Tailwind CSS e Alpine.js.

## 🛠️ Tech Stack

* **Backend:** Python, Django, Django REST Framework.
* **Frontend:** Django Templates, Tailwind CSS, Alpine.js, ApexCharts.
* **Banco de Dados:** PostgreSQL.
* **Async/Background:** Celery + Redis (para envios de WhatsApp e relatórios pesados).
* **Infraestrutura:** Docker, Docker Compose, Gunicorn, Whitenoise.

## 💻 Como Rodar Localmente

### Pré-requisitos
* Docker e Docker Compose instalados.
* Git.

### Passo a Passo

1.  **Clone o repositório:**
    ```bash
    git clone [https://github.com/seu-usuario/flowlog.git](https://github.com/seu-usuario/flowlog.git)
    cd flowlog
    ```

2.  **Configure as Variáveis de Ambiente:**
    Crie um arquivo `.env` na raiz (copie o exemplo abaixo):
    ```ini
    DEBUG=True
    SECRET_KEY=sua-chave-secreta-desenvolvimento
    ALLOWED_HOSTS=*

    # Banco de Dados (Docker)
    DB_NAME=flowlog
    DB_USER=postgres
    DB_PASSWORD=postgres
    DB_HOST=db
    DB_PORT=5432

    # Redis/Celery
    CELERY_BROKER_URL=redis://redis:6379/0
    CELERY_RESULT_BACKEND=redis://redis:6379/1
    ```

3.  **Suba o ambiente com Docker:**
    ```bash
    docker-compose up --build
    ```

4.  **Acesse:**
    * Sistema: `http://localhost:8000`
    * Login padrão: Crie um superusuário com `docker-compose exec web python manage.py createsuperuser`.

---

## 🎨 Estrutura do Projeto

* `apps/core`: Views principais (Dashboard, Relatórios).
* `apps/orders`: Lógica de pedidos e clientes.
* `apps/tenants`: Gestão de lojas/inquilinos.
* `apps/integrations`: Conexão com APIs externas (WhatsApp).
* `templates/`: Arquivos HTML com Tailwind e Alpine.js.

---

**Flowlog** © 2024 - Desenvolvido com ❤️ e Python.
