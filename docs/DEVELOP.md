# 🛠️ Guia de Desenvolvimento

Bem-vindo ao ambiente de desenvolvimento do **Flowlog**. Este documento contém tudo o que você precisa para manter e evoluir o sistema.

## 🚀 Ferramentas Core

Utilizamos o **[uv](https://github.com/astral-sh/uv)** para gestão rápida de pacotes e virtualenvs.

### Setup Inicial
```bash
# Sincroniza ambiente
uv sync

# Ativa virtualenv (se necessário para seu IDE)
source .venv/bin/activate
```

## 📋 Comandos do Dia-a-Dia

| Ação | Comando |
|------|---------|
| Rodar Servidor | `uv run manage.py runserver` |
| Criar Migrações | `uv run manage.py makemigrations` |
| Aplicar Migrações | `uv run manage.py migrate` |
| Criar Superuser | `uv run manage.py createsuperuser` |
| Shell Django | `uv run manage.py shell` |
| Rodar Celery (Local) | `uv run celery -A config worker --loglevel=info` |

## 🧪 Testes Automatizados

A base de testes utiliza o **Pytest**. Todas as novas funções de serviços devem obrigatoriamente acompanhar testes.

### Executar Testes
```bash
# Todos os testes
uv run pytest

# Por app
uv run pytest apps/orders/

# Com falha rápida
uv run pytest -x
```

### Relatório de Cobertura
```bash
uv run coverage run -m pytest
uv run coverage report
```

## 🎨 Padrões de Código (Linting)

Utilizamos o **Ruff** para garantir que o código siga as melhores práticas (PEP8).

```bash
# Checar linting
uv run ruff check .

# Formatar automaticamente
uv run ruff format .
```

## 📂 Organização da Lógica

- **Views**: Devem ser enxutas, apenas controlando a resposta HTTP.
- **Services**: Todo o cálculo e lógica de negócio vive em `apps/*/services.py`.
- **Managers**: Filtros de banco e isolamento multi-tenant ficam em `apps/*/querysets.py`.
- **Templates**: Centralizados na pasta raiz `/templates`.
