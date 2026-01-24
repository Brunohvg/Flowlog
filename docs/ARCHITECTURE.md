# 🏗️ Arquitetura do Sistema

O **Flowlog** foi desenhado seguindo a filosofia de "Monólito Modular" com forte ênfase em segurança multi-tenant e processos assíncronos.

## 📁 Estrutura de Diretórios Atualizada

```text
flowlog/
├── apps/
│   ├── accounts/     # Gestão de usuários e permissões por Loja (Tenant)
│   ├── api/          # Endpoints REST (DRF) com versionamento v1
│   ├── core/         # Lógica compartilhada, Dashboard e Middleware de Tenant
│   ├── integrations/ # Conversores e clientes (WhatsApp/Evolution, Mandaê)
│   ├── orders/       # Core Business: Pedidos, Clientes e Logística
│   ├── payments/     # Integração financeira (Pagar.me v5)
│   └── tenants/      # Configurações de domínio e isolamento de banco
├── config/           # Configurações globais (settings.py, urls.py, celery.py)
├── docs/             # Guias técnicos atualizados
└── conftest.py       # Configurações globais de testes (Pytest)
```

## 🔐 Isolamento Multi-tenant

Diferente de sistemas simples, o Flowlog implementa isolamento no nível de ORM:

1. **TenantModel**: A maioria dos models herda de `TenantModel`, que injeta automaticamente uma FK para o Tenant.
2. **TenantManager & TenantQuerySet**: Sobrescrevemos o manager padrão para que métodos como `.objects.all()` ou `.objects.filter(...)` possam ser estendidos com `.for_tenant(request.tenant)`, garantindo que uma loja nunca acesse dados de outra.
3. **Hardening**: Atributos críticos (como `tenant_id`) são protegidos via `clean()` nos modelos para impedir a transferência de dados entre lojas por engano em updates de API.

## 🔄 Arquitetura de Notificações (WhatsApp Snapshots)

Para evitar os famosos erros de "Race Condition" em sistemas assíncronos, o Flowlog utiliza **Snapshots**:

- No momento em que um evento ocorre (ex: Pedido Criado), o sistema "tira uma foto" dos dados necessários e os serializa em JSON.
- A tarefa vai para a fila do Celery com esse JSON.
- O Worker do Celery executa o envio baseando-se no snapshot congelado, **não nos dados atuais do banco**.
- Isso garante que se o entregador mudar o status 1 segundo depois do envio da tarefa para a fila, o cliente receba a notificação correta referente ao evento original.

## 💳 Fluxo de Pagamentos

- **Segurança**: Chaves de API da Pagar.me são armazenadas de forma isolada nas configurações de cada Tenant no banco de dados.
- **Resiliência**: O `PagarmeService` implementa tratamento de erros robusto para timeouts de rede e validação de payloads.
- **Webhooks**: Integrados para atualização automática do status do pedido no momento em que o Pagar.me confirma o recebimento.

## 📊 Banco de Dados (PostgreSQL)

O sistema utiliza tabelas relacionadas, mas foca em integridade de UUIDs para identificadores públicos e concorrência otimizada com `select_for_update()` em serviços de alteração de status (`OrderStatusService`).
