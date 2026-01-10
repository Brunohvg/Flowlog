# 🚀 Flowlog v2.0 - Integração Pagar.me

## 🔄 ALTERAÇÃO IMPORTANTE: Endpoint

**Endpoint:** `https://api.pagar.me/core/v5/paymentlinks`

**Formato da chave:** Aceita `sk_xxx` OU base64 (converte automaticamente)

---

## 🐛 BUGS ENCONTRADOS E CORRIGIDOS

### Bugs Corrigidos
| Bug | Descrição | Correção |
|-----|-----------|----------|
| **Endpoint errado** | Usava `/orders` com checkout embutido | Agora usa `/paymentlinks` |
| **Autenticação 401** | Formato de auth incorreto | Aceita sk_xxx (converte) ou base64 |
| **Payload incorreto** | Usava `installments` array | Usa `installments_setup` automático |
| **WhatsApp no Webhook** | `_schedule_whatsapp` fora de transação | Chamada direta `.delay()` com fallback |
| **Redis indisponível** | `kombu.exceptions.OperationalError` | Try/catch com fallback síncrono |

### Payload Correto (igual seu código de referência)
```python
payload = {
    "is_building": False,
    "name": name,
    "type": "order",
    "expires_in": 720,  # minutos
    "max_paid_sessions": 1,
    "payment_settings": {
        "accepted_payment_methods": ["credit_card"],
        "credit_card_settings": {
            "operation_type": "auth_and_capture",
            "installments_setup": {
                "interest_type": "simple",
                "max_installments": 3,
                "amount": amount_cents,
                "interest_rate": 0,
                "free_installments": 3,
            },
        },
    },
    "cart_settings": {
        "items": [{
            "amount": amount_cents,
            "name": description,
            "description": description,
            "default_quantity": 1,
        }]
    },
}
```

### Melhorias de UX Implementadas
| Item | Descrição |
|------|-----------|
| **Mensagens de erro claras** | 401 → "Chave inválida", 500 → "Temporariamente indisponível" |
| **Botão Tentar Novamente** | Modal de erro com opção de retry |
| **Link para Configurações** | Mostra hint quando erro é de API key |
| **Feedback visual de copiar** | Botão muda para "Copiado!" por 2 segundos |
| **Dashboard: Alertas coloridos** | Critical=vermelho, Warning=amarelo, Info=azul |
| **Dashboard: Links pendentes** | Alerta quando há links de pagamento aguardando |

---

## ✨ Nova Funcionalidade: Links de Pagamento

### Configurações (Pagar.me)
- Nova aba "Pagar.me" em Configurações
- Campo para Secret Key (sk_xxx)
- Toggle para ativar/desativar
- Configuração de parcelas máximas (1-3x)
- **PIX opcional** (toggle separado - requer liberação na Pagar.me)

### Links Vinculados ao Pedido
- Botão "Link de Pagamento" na tela de **detalhes do pedido**
- Botão na **lista de pedidos** (coluna Ações) - ícone de cartão verde
- Modal para escolher parcelas (1x, 2x, 3x)
- Link gerado via API Pagar.me v5
- Opções: Copiar link / Abrir checkout

### Links Avulsos (sem pedido)
- Menu lateral: **Pagamentos**
- Criar link sem pedido vinculado
- Campos: Descrição, Valor, Cliente, Parcelas
- Lista de todos os links criados com filtro por status

### Webhook Automático
- **Endpoint:** `/pagamentos/webhook/pagarme/`
- Atualiza status automaticamente
- Eventos tratados:
  - `charge.paid` - Pagamento confirmado
  - `charge.payment_failed` - Pagamento falhou
  - `order.paid` - Pedido pago
  - `order.canceled` - Pedido cancelado
  - `charge.refunded` - Estorno
- Se tem pedido vinculado: atualiza `Order.payment_status` para "PAID"
- Dispara WhatsApp de confirmação (se configurado)

### Especificações
- **API**: Pagar.me v5
- **Parcelas**: até 3x (configurável)
- **Expiração**: 12 horas
- **Checkout**: Hospedado pelo Pagar.me (seguro)
- **Métodos**: Cartão de Crédito (PIX opcional)

---

## 🔧 VARIÁVEIS DE AMBIENTE

**Nenhuma variável de ambiente nova necessária!**

A configuração do Pagar.me é feita **por tenant** através da interface:
- Configurações → Pagar.me → Secret Key

O sistema usa os dados do `TenantSettings`:
- `pagarme_enabled` (boolean)
- `pagarme_api_key` (string)
- `pagarme_max_installments` (int: 1-3)
- `pagarme_pix_enabled` (boolean)

---

## 📋 Migrations

### Tenants
```
0006_pagarme_fields.py
- pagarme_enabled
- pagarme_api_key  
- pagarme_max_installments
- pagarme_pix_enabled
```

### Payments (novo app)
```
0001_initial.py
- Tabela: payments_paymentlink
```

---

## 🔧 Configuração do Webhook no Pagar.me

1. Acesse o Dashboard Pagar.me
2. Vá em **Configurações → Webhooks**
3. Adicione a URL:
   ```
   https://seu-dominio.com.br/pagamentos/webhook/pagarme/
   ```
4. Selecione os eventos:
   - `paymentlink.paid` ← Link de pagamento pago
   - `paymentlink.canceled` ← Link cancelado
   - `order.paid`
   - `order.canceled`
   - `charge.paid`
   - `charge.payment_failed`
   - `charge.refunded`

---

## 📦 Deploy

```bash
# 1. Build
./deploy.sh  # Tag: v2.0

# 2. Portainer: Update stack para v2.0

# 3. Migrations rodam automaticamente:
# - tenants: 0006_pagarme_fields
# - payments: 0001_initial

# 4. Configurar no sistema:
# Configurações → Pagar.me → Adicionar Secret Key → Ativar
```

---

## ⚠️ IMPORTANTE: Migrations

Se você teve erro de migrations duplicadas (como `duplicate column name: motoboy_fee`), siga estes passos:

### Para ambiente LOCAL (SQLite):
```bash
# Delete o banco local e recrie
rm db.sqlite3
python manage.py migrate
python manage.py createsuperuser
```

### Para PRODUÇÃO (se já rodou migrations conflitantes):
```bash
# Conecte no container web
docker exec -it flowlog_web_1 bash

# Verifique as migrations aplicadas
python manage.py showmigrations orders

# Se necessário, fake a migration problemática
python manage.py migrate orders 0005_order_motoboy_fields --fake

# Depois aplique as novas
python manage.py migrate
```

---

## 🔒 Segurança

- Secret Key nunca exposta no frontend
- Checkout hospedado pelo Pagar.me (PCI DSS compliant)
- Links expiram em 12 horas
- Webhook valida eventos do Pagar.me

---

## Inclui também (v1.9)

- ✅ Log de erros Celery (não mais silencioso)
- ✅ Limite loop pickup_code (máx 50 tentativas)
- ✅ ALLOWED_HOSTS mais seguro
- ✅ Menu lateral sem scroll
- ✅ Nome da loja dinâmico na etiqueta

---

## 📁 Arquivos Criados/Modificados

### Novos (app payments)
```
apps/payments/
├── __init__.py
├── admin.py
├── apps.py
├── models.py          # PaymentLink
├── services.py        # PagarmeService
├── urls.py
├── views.py
└── migrations/
    └── 0001_initial.py

templates/payments/
├── payment_link_list.html
├── payment_link_detail.html
└── create_standalone.html
```

### Modificados
```
config/settings.py          # INSTALLED_APPS
config/urls.py              # URL payments
apps/tenants/models.py      # Campos pagarme_*
apps/tenants/migrations/0006_pagarme_fields.py
apps/core/views.py          # save_pagarme
templates/base/base.html    # Menu Pagamentos
templates/settings/settings.html  # Aba Pagar.me
apps/orders/templates/orders/order_list.html    # Botão na tabela
apps/orders/templates/orders/order_detail.html  # Botão e modal
```
