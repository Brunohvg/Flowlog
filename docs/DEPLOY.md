### 2. Arquivo `DEPLOY.md`

Crie este arquivo na raiz do projeto. Ele é o teu manual técnico para colocar o site no ar via Portainer/Docker Hub.

```markdown
# ☁️ Guia de Deploy e Infraestrutura

Este documento descreve o processo de publicação do **Flowlog** utilizando Docker Hub e Portainer (Docker Swarm).

## 🔄 Fluxo de Trabalho

1.  **Local:** Desenvolvimento e testes na máquina local.
2.  **Build & Push:** O script `deploy.sh` constrói a imagem e envia para o Docker Hub.
3.  **Deploy:** O Portainer baixa a nova imagem e atualiza os serviços na nuvem.

---

## 1. Build e Envio para Docker Hub

Utilize o script automatizado na raiz do projeto.

### Pré-requisitos
* Conta no [Docker Hub](https://hub.docker.com/).
* Login realizado no terminal: `docker login`.

### Executando o Deploy
No terminal da sua máquina local:

```bash
chmod +x deploy.sh  # Apenas na primeira vez
./deploy.sh

```

1. O script pedirá a **TAG da versão** (ex: `v1.0`, `fix-layout`).
2. Ele fará o build da imagem automaticamente.
3. Ele enviará para o Docker Hub com duas tags: `brunobh51/flowlog:TAG` e `brunobh51/flowlog:latest`.

---

## 2. Configuração no Portainer (Produção)

Acesse o seu Portainer e crie uma nova **Stack** com o nome `flowlog`.

### A. Variáveis de Ambiente (Environment Variables)

Adicione estas variáveis na aba "Environment variables" da Stack:

* `DEBUG`: `False`
* `SECRET_KEY`: *(Gere uma chave aleatória e segura)*
* `ALLOWED_HOSTS`: `flowlog.lojabibelo.com.br` *(ou seu domínio)*
* `CSRF_TRUSTED_ORIGINS`: `https://flowlog.lojabibelo.com.br`
* `DB_HOST`: `db`
* `DB_NAME`: `flowlog`
* `DB_USER`: `flowlog_user`
* `DB_PASSWORD`: *(Senha forte do banco)*
* `CELERY_BROKER_URL`: `redis://redis:6379/0`
* `CELERY_RESULT_BACKEND`: `redis://redis:6379/1`

### B. Definição da Stack (docker-compose.yml)

Copie e cole este conteúdo no editor Web do Portainer:

```yaml
version: '3.8'

services:
  # --- APLICAÇÃO WEB ---
  web:
    image: brunobh51/flowlog:latest
    command: gunicorn config.wsgi:application --bind 0.0.0.0:8000
    volumes:
      - static_volume:/app/staticfiles
      - media_volume:/app/media
    networks:
      - flowlog_net
    deploy:
      replicas: 1
      restart_policy:
        condition: on-failure
      update_config:
        order: start-first

  # --- WORKER (TAREFAS EM 2º PLANO) ---
  worker:
    image: brunobh51/flowlog:latest
    command: celery -A config worker -l info
    networks:
      - flowlog_net
    deploy:
      replicas: 1
      restart_policy:
        condition: on-failure

  # --- BANCO DE DADOS ---
  db:
    image: postgres:15-alpine
    volumes:
      - postgres_data:/var/lib/postgresql/data
    environment:
      - POSTGRES_DB=flowlog
      - POSTGRES_USER=flowlog_user
      - POSTGRES_PASSWORD=${DB_PASSWORD}
    networks:
      - flowlog_net
    deploy:
      placement:
        constraints: [node.role == manager]

  # --- REDIS (CACHE/BROKER) ---
  redis:
    image: redis:7-alpine
    networks:
      - flowlog_net

  # --- NGINX (PROXY REVERSO) ---
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"  # Porta externa : Porta interna
    volumes:
      - static_volume:/usr/share/nginx/html/static
      - media_volume:/usr/share/nginx/html/media
      # Crie um config map no Portainer para o nginx.conf se necessário
    depends_on:
      - web
    networks:
      - flowlog_net

networks:
  flowlog_net:
    driver: overlay

volumes:
  postgres_data:
  static_volume:
  media_volume:

```

---

## 3. Atualizando a Versão (Redeploy)

Sempre que você rodar o `./deploy.sh` e enviar uma nova versão:

1. Vá ao **Portainer** > **Stacks** > **Flowlog**.
2. Clique na aba **Editor**.
3. Clique no botão **Update the stack**.
4. ⚠️ **IMPORTANTE:** Marque a opção ✅ **"Re-pull image and redeploy"**.
5. Clique em **Update**.

O Portainer baixará a nova imagem e atualizará o sistema sem downtime.

---

## 4. Comandos Administrativos

Para rodar comandos como criar superusuário ou migrar banco em produção:

1. No Portainer, vá em **Containers**.
2. Encontre o container `flowlog_web`.
3. Clique no ícone **Console (>_)** e depois em **Connect**.
4. Execute os comandos:

```bash
# Aplicar migrações (se necessário)
python manage.py migrate

# Se houver conflito de migrations, rode:
python manage.py makemigrations --merge
python manage.py migrate

# Criar superusuário
python manage.py createsuperuser

```

---

## 5. Resolução de Conflitos de Migrations

Se aparecer erro de "Conflicting migrations detected":

```bash
# 1. Primeiro, faça o merge das migrations
python manage.py makemigrations --merge

# 2. Depois aplique
python manage.py migrate
```

Isso é normal quando há desenvolvimento paralelo.

```

```
