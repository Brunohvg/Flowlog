# Usa uma imagem Python leve e moderna
FROM python:3.12-slim

# Variáveis de ambiente
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Dependências de sistema
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Diretório de trabalho
WORKDIR /app

# Copia o requirements gerado pelo uv (AQUI está a correção)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código do projeto
COPY . .

# Coleta arquivos estáticos (não falha o build se faltar env)
RUN SECRET_KEY=build_secret \
    DEBUG=False \
    python manage.py collectstatic --noinput || true

# Usuário não-root
RUN adduser --disabled-password --no-create-home django-user
USER django-user

# Porta
EXPOSE 8000

# Comando padrão
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
