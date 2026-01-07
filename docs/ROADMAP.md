# 🗺️ Flowlog - Roadmap de Melhorias

> Sugestões de implementações futuras organizadas por prioridade

---

## 🔴 Prioridade Alta (Próximas Versões)

### 1. Relatórios Exportáveis
**Complexidade:** Média | **Estimativa:** 2-3 dias

```
Funcionalidades:
- Exportar relatório para PDF (ReportLab ou WeasyPrint)
- Exportar relatório para Excel (openpyxl)
- Filtros aplicados mantidos na exportação
- Logo da empresa no cabeçalho

Arquivos a criar/modificar:
- apps/core/exports.py (novo)
- apps/core/views.py (adicionar endpoints)
- templates/reports/reports.html (botões de export)
- requirements.txt (adicionar libs)
```

### 2. Comissão por Vendedor
**Complexidade:** Média | **Estimativa:** 2-3 dias

```
Funcionalidades:
- Campo percentual de comissão por usuário
- Cálculo automático por pedido concluído
- Relatório de comissões por período
- Apenas pedidos pagos e não cancelados contam

Modelo:
- User.commission_rate (DecimalField, default=0)
- Order.commission_value (calculado)

Arquivos a criar/modificar:
- apps/accounts/models.py (adicionar campo)
- apps/orders/models.py (adicionar campo calculado)
- apps/core/views.py (relatório de comissões)
- templates/reports/commissions.html (novo)
```

### 3. Múltiplas Formas de Pagamento
**Complexidade:** Média | **Estimativa:** 2-3 dias

```
Funcionalidades:
- PIX, Cartão Crédito, Cartão Débito, Boleto, Dinheiro
- Múltiplos pagamentos por pedido (parcial)
- Histórico de pagamentos
- Conciliação financeira

Modelos:
- PaymentMethod (choices: pix, credit, debit, boleto, cash)
- Payment (order, method, amount, date, notes)

Arquivos a criar/modificar:
- apps/orders/models.py (novo modelo Payment)
- apps/orders/views.py (gestão de pagamentos)
- templates/orders/order_detail.html (seção pagamentos)
```

### 4. Catálogo de Produtos
**Complexidade:** Alta | **Estimativa:** 4-5 dias

```
Funcionalidades:
- CRUD de produtos (nome, preço, SKU, ativo)
- Vincular produtos ao pedido (OrderItem)
- Cálculo automático do valor total
- Busca rápida de produtos

Modelos:
- Product (tenant, name, sku, price, active)
- OrderItem (order, product, quantity, unit_price)

Arquivos a criar/modificar:
- apps/products/ (novo app)
- apps/orders/models.py (OrderItem)
- templates/orders/order_create.html (seletor de produtos)
```

### 5. Busca Avançada
**Complexidade:** Baixa | **Estimativa:** 1 dia

```
Funcionalidades:
- Busca por código, cliente, telefone
- Filtro por período (data início/fim)
- Filtro por valor (mín/máx)
- Combinação de filtros
- Salvar filtros favoritos

Arquivos a modificar:
- apps/orders/views.py (melhorar order_list)
- templates/orders/order_list.html (mais filtros)
```

---

## 🟡 Prioridade Média (Futuro Próximo)

### 6. PWA (Progressive Web App)
**Complexidade:** Baixa | **Estimativa:** 1 dia

```
Funcionalidades:
- Instalável no celular/desktop
- Ícone na home screen
- Splash screen personalizada
- Funciona offline (cache básico)

Arquivos a criar:
- static/manifest.json
- static/service-worker.js
- templates/base/base.html (meta tags)
- static/icons/ (ícones em vários tamanhos)
```

### 7. Tema Escuro
**Complexidade:** Baixa | **Estimativa:** 1 dia

```
Funcionalidades:
- Toggle claro/escuro
- Respeitar preferência do sistema
- Persistir escolha (localStorage)
- Transição suave

Arquivos a modificar:
- templates/base/base.html (toggle + script)
- static/css/dark-mode.css (novo)
- Todas as cores via CSS variables
```

### 8. Notificações Push (Browser)
**Complexidade:** Média | **Estimativa:** 2 dias

```
Funcionalidades:
- Notificar novos pedidos
- Notificar falhas de entrega
- Notificar retiradas expirando
- Configurável por usuário

Tecnologia:
- Web Push API
- Service Worker
- django-webpush

Arquivos a criar:
- apps/notifications/ (novo app)
- Service worker atualizado
```

### 9. Atalhos de Teclado
**Complexidade:** Baixa | **Estimativa:** 0.5 dia

```
Atalhos sugeridos:
- N = Novo pedido
- / = Focar busca
- E = Editar (no detalhe)
- P = Marcar pago
- Esc = Fechar modal

Arquivos a modificar:
- templates/base/base.html (script de atalhos)
- Tooltip nos botões mostrando atalho
```

### 10. Logs de Auditoria
**Complexidade:** Média | **Estimativa:** 2 dias

```
Funcionalidades:
- Registrar todas as ações (criar, editar, deletar)
- Quem fez, quando, o quê mudou
- Visualização por pedido
- Filtro por usuário/ação/período

Modelo:
- AuditLog (user, action, model, object_id, changes, timestamp)

Pacote sugerido:
- django-auditlog (pronto)
```

---

## 🟢 Prioridade Técnica (Escalabilidade)

### 11. API REST
**Complexidade:** Alta | **Estimativa:** 5-7 dias

```
Funcionalidades:
- CRUD completo de pedidos, clientes
- Autenticação via Token/JWT
- Rate limiting
- Documentação Swagger/OpenAPI

Tecnologia:
- Django REST Framework
- drf-spectacular (docs)
- djangorestframework-simplejwt

Endpoints:
- /api/v1/orders/
- /api/v1/customers/
- /api/v1/reports/
```

### 12. Webhooks
**Complexidade:** Média | **Estimativa:** 2-3 dias

```
Funcionalidades:
- Notificar sistemas externos sobre eventos
- Configurável por tenant
- Retry automático em falhas
- Log de entregas

Eventos:
- order.created
- order.confirmed
- order.shipped
- order.delivered
- order.cancelled

Modelo:
- Webhook (tenant, url, events, secret, active)
- WebhookDelivery (webhook, event, payload, status, attempts)
```

### 13. Testes Automatizados
**Complexidade:** Média | **Estimativa:** 3-4 dias

```
Cobertura sugerida:
- Models (validações, métodos)
- Views (status codes, permissões)
- Services (lógica de negócio)
- Integrations (mocks da Evolution API)

Ferramentas:
- pytest + pytest-django
- factory_boy (fixtures)
- coverage (relatório)

Meta: 80% de cobertura
```

### 14. Cache com Redis
**Complexidade:** Baixa | **Estimativa:** 1 dia

```
O que cachear:
- Dashboard stats (5 min)
- Relatórios (15 min)
- Configurações do tenant (1 hora)

Configuração:
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': 'redis://redis:6379/2',
    }
}
```

### 15. Rate Limiting
**Complexidade:** Baixa | **Estimativa:** 0.5 dia

```
Limites sugeridos:
- Login: 5 tentativas/min
- API: 100 requests/min
- WhatsApp: 30 mensagens/min

Pacote:
- django-ratelimit
```

---

## 🔵 Ideias Futuras (Backlog)

| Ideia | Descrição |
|-------|-----------|
| **Multi-idioma** | Suporte a inglês/espanhol |
| **Importação CSV** | Importar pedidos/clientes em massa |
| **Integração Correios** | Buscar status automaticamente |
| **Integração iFood** | Receber pedidos do iFood |
| **Chat interno** | Comunicação entre vendedores |
| **App Mobile** | React Native / Flutter |
| **BI Dashboard** | Metabase / Grafana embedded |
| **Assinatura** | Pedidos recorrentes |

---

## 📋 Template para Nova Feature

```markdown
## Nome da Feature

**Prioridade:** Alta/Média/Baixa
**Complexidade:** Baixa/Média/Alta
**Estimativa:** X dias

### Descrição
O que a feature faz e por que é importante.

### Requisitos Funcionais
- [ ] RF01: ...
- [ ] RF02: ...

### Requisitos Técnicos
- [ ] RT01: ...
- [ ] RT02: ...

### Modelos
- Model1 (campo1, campo2)
- Model2 (campo1, campo2)

### Arquivos a Modificar
- arquivo1.py
- arquivo2.html

### Dependências
- pacote1
- pacote2

### Critérios de Aceite
- [ ] Funciona no cenário X
- [ ] Funciona no cenário Y
- [ ] Testes passando
- [ ] Documentação atualizada
```

---

## 🎯 Sugestão de Ordem de Implementação

1. **v12:** Busca Avançada + Atalhos de Teclado (quick wins)
2. **v13:** Relatórios Exportáveis (PDF/Excel)
3. **v14:** Comissão por Vendedor
4. **v15:** Múltiplas Formas de Pagamento
5. **v16:** PWA + Tema Escuro
6. **v17:** API REST
7. **v18:** Catálogo de Produtos
8. **v19:** Webhooks + Logs de Auditoria
9. **v20:** Testes Automatizados (80% cobertura)

---

*Roadmap atualizado em Janeiro 2026*
