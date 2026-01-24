# 🚀 Guia de Deploy

O Flowlog está preparado para ambientes de alta disponibilidade utilizando **Docker** e **Docker Swarm**.

## 🐋 Infraestrutura com Docker

A plataforma é composta por 5 serviços principais:
- **web**: Servidor Django (Uvicorn/Gunicorn).
- **worker**: Processador de tarefas em segundo plano (WhatsApp/Financeiro).
- **beat**: Agendador de tarefas periódicas.
- **db**: PostgreSQL.
- **redis**: Broker de mensagens para o Celery.

### Requisitos Mínimos
- Docker 24+
- Docker Compose v2+
- Servidor Linux (Ubuntu 22.04 recomendado)

## 🛠️ Passo a Passo do Deploy

### 1. Clonagem e Configuração
```bash
git clone <url-do-repositorio> && cd flowlog
cp .env.example .env
# Edite o .env com os dados de produção!
```

### 2. Build e Inicialização (Docker Compose)
Para um deploy rápido ou ambiente de staging:
```bash
docker compose up -d --build
```

### 3. Migrações e Estáticos
```bash
docker compose exec web python manage.py migrate
docker compose exec web python manage.py collectstatic --noinput
```

## ⚙️ Variáveis de Ambiente Críticas (Produção)

| Variável | Valor Recomendado |
|----------|-------------------|
| `DEBUG` | `False` |
| `ALLOWED_HOSTS` | `meudominio.com.br` |
| `DATABASE_URL` | `postgres://user:pass@db:5432/flowlog` |
| `CELERY_BROKER_URL` | `redis://redis:6379/0` |
| `SENTRY_DSN` | URL do seu projeto Sentry para monitoramento de erros |

## 🔒 Segurança

- **SSL**: Utilize um Proxy Reverso como **Nginx** ou **Traefik** para gerenciar Certificados SSL (Let's Encrypt).
- **HSTS**: Já configurado no `settings.py` para ser ativado quando `DEBUG=False`.
- **Admin Path**: Recomendamos alterar a variável `DJANGO_ADMIN_PATH` no `.env` para algo secreto.

---

## 📈 Monitoramento

Acompanhe os logs em tempo real:
```bash
docker compose logs -f web
docker compose logs -f worker
```
