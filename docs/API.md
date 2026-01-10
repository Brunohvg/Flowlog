# 🔌 Flowlog API REST

API REST para integração com sistemas externos.

## 🔐 Autenticação

A API suporta dois métodos:

### Session Authentication (navegador)
Usado automaticamente quando logado no sistema.

### Basic Authentication (integração)
```bash
curl -u usuario:senha https://flowlog.app/api/v1/orders/
```

## 📍 Endpoints

Base URL: `https://seu-dominio.com/api/v1/`

### Customers (Clientes)

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/customers/` | Listar clientes |
| GET | `/customers/{id}/` | Buscar cliente |
| POST | `/customers/` | Criar cliente |
| PUT | `/customers/{id}/` | Atualizar cliente |
| DELETE | `/customers/{id}/` | Remover cliente |

**Criar Cliente:**
```json
POST /api/v1/customers/
{
    "name": "João Silva",
    "phone": "31999999999",
    "email": "joao@email.com",
    "cpf": "123.456.789-00",
    "notes": "Cliente VIP"
}
```

### Orders (Pedidos)

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/orders/` | Listar pedidos |
| GET | `/orders/{id}/` | Buscar pedido |
| POST | `/orders/` | Criar pedido |
| PATCH | `/orders/{id}/status/` | Atualizar status |
| POST | `/orders/{id}/payment-link/` | Criar link pagamento |

**Criar Pedido (cliente existente):**
```json
POST /api/v1/orders/
{
    "customer_id": "uuid-do-cliente",
    "total_value": 150.00,
    "notes": "Entregar após 18h",
    "delivery_type": "motoboy",
    "delivery_address": "Rua Y, 200 - BH/MG"
}
```

**Criar Pedido (cliente novo):**
```json
POST /api/v1/orders/
{
    "customer_name": "Maria Santos",
    "customer_phone": "31988888888",
    "customer_email": "maria@email.com",
    "total_value": 200.00,
    "delivery_type": "pickup"
}
```

**Atualizar Status:**
```json
PATCH /api/v1/orders/{id}/status/
{
    "order_status": "confirmed",
    "payment_status": "paid"
}
```

**Status disponíveis:**
- `order_status`: pending, confirmed, completed, cancelled, returned
- `payment_status`: pending, paid, refunded
- `delivery_status`: pending, shipped, delivered, ready_for_pickup, picked_up, failed_attempt, expired

### Payment Links (Links de Pagamento)

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/payment-links/` | Listar links |
| GET | `/payment-links/{id}/` | Buscar link |
| POST | `/payment-links/` | Criar link |

**Criar Link para Pedido:**
```json
POST /api/v1/payment-links/
{
    "order_id": "uuid-do-pedido",
    "installments": 3
}
```

**Criar Link Avulso:**
```json
POST /api/v1/payment-links/
{
    "amount": 500.00,
    "description": "Produto X",
    "customer_name": "Cliente Y",
    "customer_phone": "31999999999",
    "installments": 2
}
```

### Dashboard (Estatísticas)

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/dashboard/` | Métricas do dia/mês |

**Resposta:**
```json
{
    "orders_today": 15,
    "orders_pending": 3,
    "orders_month": 150,
    "revenue_today": "1500.00",
    "revenue_month": "45000.00",
    "ticket_medio": "300.00"
}
```

## 🔍 Filtros

### Orders
```
GET /api/v1/orders/?status=pending
GET /api/v1/orders/?payment=paid
GET /api/v1/orders/?delivery=shipped
GET /api/v1/orders/?date_from=2024-01-01&date_to=2024-01-31
```

### Payment Links
```
GET /api/v1/payment-links/?status=pending
GET /api/v1/payment-links/?status=paid
```

### Customers
```
GET /api/v1/customers/?search=joao
```

## 📄 Paginação

Todas as listas são paginadas:

```json
{
    "count": 150,
    "next": "https://flowlog.app/api/v1/orders/?page=2",
    "previous": null,
    "results": [...]
}
```

## 📖 Documentação Interativa

- **Swagger UI:** `/api/docs/`
- **ReDoc:** `/api/redoc/`
- **Schema OpenAPI:** `/api/schema/`

## ⚠️ Erros

```json
{
    "error": "Descrição do erro"
}
```

| Código | Descrição |
|--------|-----------|
| 400 | Dados inválidos |
| 401 | Não autenticado |
| 403 | Sem permissão |
| 404 | Não encontrado |
| 500 | Erro interno |
