# 🚀 Guia de Deploy Seguro - Flowlog

Este guia descreve o processo de deploy em produção para o sistema Flowlog.

## 📋 Pré-requisitos

- **Python:** 3.13+
- **Database:** PostgreSQL 15+
- **Cache/Broker:** Redis 7+
- **Worker:** Celery 5.4+
- **API Externa:** Evolution API (conectada e com instâncias criadas)

## 🛠 Passo a Passo de Deploy

### 1. Preparação (Branching)
- Use sempre a branch `main` ou `production` para deploy.
- **NUNCA** faça deploy direto de branches de desenvolvimento.

### 2. Atualização do Código
```bash
git pull origin main
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Migrations (Ponto Crítico)
Antes de rodar, verifique se existem migrations que alteram colunas já criadas manualmente.
```bash
# Verifique migrations pendentes
python manage.py showmigrations

# Se necessário, fakeie migrations de colunas existentes (ver DEPLOY.md)
# python manage.py migrate <app> <migration_name> --fake

# Rode migrations normais
python manage.py migrate
```

### 4. Coleta de Estáticos
```bash
python manage.py collectstatic --no-input
```

### 5. Reinício de Serviços
É crucial reiniciar os workers para carregar as novas tasks.

**Web (Django/Gunicorn):**
```bash
sudo systemctl restart flowlog-web
```

**Workers Celery:**
```bash
sudo systemctl restart flowlog-worker-default
sudo systemctl restart flowlog-worker-whatsapp
```

## ✅ Checklists

### Pré-Deploy
- [ ] Validar conexão com banco de dados.
- [ ] Validar conexão com Redis (`redis-cli ping`).
- [ ] Verificar se as credenciais da Evolution API no `.env` estão corretas.

### Pós-Deploy
- [ ] Verificar `logs/django.log` por erros de importação.
- [ ] Acessar `Admin > Integrations > Notification Logs` e verificar se novas notificações estão entrando como `sent`.
- [ ] Testar uma atualização de status manual em um pedido de teste.

## 🔄 Estratégia de Rollback

Caso ocorra um erro crítico após o deploy:

1. **Reverter Código:**
   ```bash
   git checkout <tag_anterior_ou_hash>
   ```
2. **Reiniciar Serviços:**
   Reinicie Web e Workers imediatamente.
3. **Database:**
   Evite `migrate <app> <prev_migration>` em produção se possível. Prefira corrigir o código para compatibilidade com o estado atual do banco.

## ⚠️ Pontos de Atenção
- **Workers Ativos:** O sistema depende da fila `whatsapp` estar sendo processada. Se o worker cair, as notificações ficarão paradas no Redis.
- **Snapshot:** Lembre-se que as mensagens enviadas usam o estado do objeto no momento em que a task foi criada.
