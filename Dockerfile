# Usa uma imagem Python leve e moderna
FROM python:3.12-slim

# Define variáveis de ambiente para evitar arquivos .pyc e logs em buffer
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Instala dependências do sistema necessárias para o PostgreSQL e compilação
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Cria diretório de trabalho
WORKDIR /app

# Copia os arquivos de configuração de dependências
COPY pyproject.toml .

# Instala as dependências (incluindo gunicorn que já está no teu toml)
RUN pip install --no-cache-dir .

# Copia o código do projeto
COPY . .

# Coleta os arquivos estáticos (CSS, JS) para a pasta staticfiles
# Nota: Precisamos de variáveis dummy aqui pois o settings valida o .env
RUN SECRET_KEY=build_secret \
    DEBUG=False \
    python manage.py collectstatic --noinput

# Cria usuário não-root por segurança
RUN adduser --disabled-password --no-create-home django-user
USER django-user

# Expõe a porta 8000
EXPOSE 8000

# Comando padrão (pode ser sobrescrito no docker-compose)
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
