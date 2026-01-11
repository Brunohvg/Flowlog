# 🚀 Instruções de Deploy - Flowlog v2.4

## 📦 Banco NOVO (Local/SQLite)

```bash
# Apague o banco antigo se existir
rm -f db.sqlite3

# Rode as migrations
python manage.py migrate

# Crie um superusuário
python manage.py createsuperuser

# Inicie o servidor
python manage.py runserver
```

---

## 🏭 Banco EXISTENTE (Produção/PostgreSQL)

### Se as colunas JÁ EXISTEM no banco:

O erro `column "motoboy_fee" already exists` acontece porque as colunas foram criadas manualmente ou por uma versão anterior.

**Solução: Marcar migrations como aplicadas SEM executar**

```bash
# 1. Verificar quais migrations estão pendentes
python manage.py showmigrations orders tenants

# 2. Marcar as migrations de orders como "já aplicadas"
python manage.py migrate orders 0002_order_new_fields --fake

# 3. Marcar as migrations de tenants como "já aplicadas"  
python manage.py migrate tenants 0008_payment_failed_fields --fake

# 4. Rodar migrations restantes normalmente
python manage.py migrate
```

### Se as colunas NÃO EXISTEM:

```bash
# Rode normalmente
python manage.py migrate
```

---

## 🔍 Como verificar se colunas existem

### PostgreSQL:
```sql
SELECT column_name FROM information_schema.columns 
WHERE table_name = 'orders_order' AND column_name IN ('motoboy_fee', 'pickup_code', 'sale_date');
```

### SQLite:
```sql
PRAGMA table_info(orders_order);
```

---

## 📋 Migrations nesta versão

| App | Migration | Campos |
|-----|-----------|--------|
| orders | 0002_order_new_fields | pickup_code, sale_date, motoboy_fee, motoboy_paid |
| tenants | 0008_payment_failed_fields | notify_payment_failed, msg_payment_failed |

---

## ⚠️ Importante

- **NUNCA delete migrations em produção** - use `--fake` para pular
- **Sempre faça backup** antes de rodar migrations
- As migrations são **idempotentes** - se a coluna existe, use `--fake`
