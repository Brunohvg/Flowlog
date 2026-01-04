# 📘 Documentação Completa – Sistema de Pedidos (Entrega + Retirada)

Esta documentação consolida **tudo o que foi implementado**, corrige as falhas levantadas ao longo do desenvolvimento e apresenta a **implementação completa e estável** da funcionalidade de **retirada na loja**, **sem regressão** do que já existia.

O objetivo é que este documento sirva como:

* fonte única da verdade do domínio
* guia de implementação
* base para futuras evoluções

---

## 1. Visão Geral do Domínio

O sistema de pedidos suporta **dois modos de atendimento**:

* 📦 **Entrega** no endereço do cliente
* 🏬 **Retirada na loja**, após liberação

Esses modos **coexistem**, não se substituem e não compartilham regras indevidas.

---

## 2. Conceitos Fundamentais

### 2.1 Tenant

Todo dado pertence a um **tenant** (empresa).
Nenhuma query ou ação ignora o tenant.

---

### 2.2 Pedido (`Order`)

O pedido é a **entidade central** do sistema.
Ele possui **múltiplos estados**, cada um com responsabilidade clara.

#### Status do Pedido (`OrderStatus`)

* `pending` → pedido criado
* `confirmed` → confirmado (ex: retirada liberada)
* `completed` → finalizado
* `cancelled` → cancelado

> Representa o **ciclo de vida comercial** do pedido.

---

#### Status de Pagamento (`PaymentStatus`)

* `pending`
* `paid`

> Independe de entrega ou retirada.

---

#### Tipo de Entrega (`DeliveryType`)

* `delivery` → entrega ao cliente
* `pickup` → retirada na loja

> Define **qual fluxo de entrega será aplicado**.

---

#### Status de Entrega (`DeliveryStatus`)

* `pending` → aguardando ação
* `shipped` → enviado (somente entrega)
* `delivered` → entregue (somente entrega)
* `ready_for_pickup` → pronto para retirada (somente retirada)

> Este status **depende do `delivery_type`**.

---

## 3. Regras de Negócio (Consolidadas)

### 3.1 Entrega

* `delivery_type = delivery`
* fluxo: `pending → shipped → delivered`
* endereço é obrigatório

### 3.2 Retirada na Loja

* `delivery_type = pickup`
* fluxo: `pending → ready_for_pickup`
* **não possui endereço**
* ao liberar retirada:

  * `delivery_status = ready_for_pickup`
  * `order_status = confirmed`

### 3.3 Regras Importantes

* pedido de retirada **não pode ser enviado**
* pedido de entrega **não pode ser liberado para retirada**
* views **não possuem regra de negócio**
* services são a fonte da verdade

---

## 4. Implementação Técnica

### 4.1 Models (estado final, sem regressão)

```python
class DeliveryStatus(models.TextChoices):
    PENDING = "pending", "Pendente"
    SHIPPED = "shipped", "Enviado"
    DELIVERED = "delivered", "Entregue"
    READY_FOR_PICKUP = "ready_for_pickup", "Pronto para retirada"
```

> ÚNICA extensão feita no model existente.

Todo o restante do model `Order` permanece **exatamente como já implementado**, incluindo:

* `payment_status`
* `status_display`
* `can_be_cancelled`
* índices
* código do pedido

---

### 4.2 Services

#### Criação de Pedido

```python
class OrderService:
    @transaction.atomic
    def create_order(self, *, tenant, seller, data):
        phone = data["customer_phone"]
        phone_normalized = "".join(filter(str.isdigit, phone))

        customer, _ = Customer.objects.for_tenant(tenant).get_or_create(
            phone_normalized=phone_normalized,
            defaults={
                "name": data["customer_name"],
                "phone": phone,
                "tenant": tenant,
            },
        )

        delivery_type = data.get("delivery_type", DeliveryType.DELIVERY)

        order = Order.objects.create(
            tenant=tenant,
            customer=customer,
            seller=seller,
            total_value=data["total_value"],
            delivery_type=delivery_type,
            delivery_address=(
                "" if delivery_type == DeliveryType.PICKUP
                else data.get("delivery_address", "")
            ),
            notes=data.get("notes", ""),
        )

        return order
```

---

#### Liberação para Retirada

```python
class OrderStatusService:
    @transaction.atomic
    def mark_ready_for_pickup(self, *, order, actor):
        if order.tenant_id != actor.tenant_id:
            raise ValueError("Usuário não pertence ao tenant.")

        if order.delivery_type != DeliveryType.PICKUP:
            raise ValueError("Pedido não é para retirada.")

        if order.delivery_status == DeliveryStatus.READY_FOR_PICKUP:
            return order

        order.delivery_status = DeliveryStatus.READY_FOR_PICKUP
        order.order_status = OrderStatus.CONFIRMED
        order.save(update_fields=["delivery_status", "order_status", "updated_at"])

        return order
```

---

### 4.3 Views (FBV estáveis)

```python
@login_required
def order_ready_for_pickup(request, order_id):
    order = get_object_or_404(
        Order.objects.for_tenant(request.tenant),
        id=order_id,
    )

    OrderStatusService().mark_ready_for_pickup(
        order=order,
        actor=request.user,
    )

    return redirect("order_list")
```

---

### 4.4 URLs

```python
path(
    "<uuid:order_id>/retirada/",
    order_ready_for_pickup,
    name="order_ready_for_pickup",
),
```

---

## 5. Frontend

### 5.1 Formulário de Pedido

* campo `delivery_type`
* se `pickup`, endereço desabilitado
* endereço gerado automaticamente apenas para entrega

---

### 5.2 Lista de Pedidos

* exibe tipo (Entrega / Retirada)
* exibe status correto
* botão **Liberar retirada** aparece somente quando:

  * `delivery_type == pickup`
  * `delivery_status == pending`

---

### 5.3 Etiqueta de Pedido

* sempre disponível
* mostra:

  * código
  * cliente
  * tipo
  * endereço **ou** “RETIRADA NA LOJA”

---

## 6. Falhas Corrigidas

* ❌ mistura de refatoração com feature
* ❌ regressão de campos do model
* ❌ regras espalhadas em views
* ❌ ações incorretas por GET

Tudo foi centralizado e estabilizado.

---

## 7. Estado Atual do Projeto

✔ Domínio fechado
✔ Retirada implementada corretamente
✔ Nenhuma funcionalidade removida
✔ Base sólida para evolução

---

## 8. Próximas Evoluções (opcional)

* WhatsApp específico para retirada
* Dashboard
* Permissões
* Testes automatizados

---

**Este documento representa o estado correto e estável do sistema.**

---

# 🧱 ATUALIZAÇÃO — PEDIDOS COM RETIRADA NA LOJA (ETAPA CONCLUÍDA)

> **Status:** ✅ IMPLEMENTADO, ESTÁVEL E EM PRODUÇÃO LOCAL

Esta seção documenta a **finalização completa da feature de Retirada na Loja**, incluindo ajustes de domínio, services, views, URLs e templates.

---

## 9. Fluxos de Pedido (Estado Atual)

### 9.1 Entrega

**delivery_type = `delivery`**

Fluxo:

```
PENDING → SHIPPED → DELIVERED
```

Regras:

* endereço obrigatório
* pode ser enviado
* pode ser entregue
* etiqueta exibe endereço

---

### 9.2 Retirada na Loja

**delivery_type = `pickup`**

Fluxo:

```
PENDING → READY_FOR_PICKUP → COMPLETED
```

Regras:

* endereço NÃO é salvo
* pedido NÃO pode ser enviado
* pedido pode ser liberado para retirada
* etiqueta exibe “RETIRADA NA LOJA”

---

## 10. Modelos (Estado Final)

### 10.1 DeliveryStatus

```python
class DeliveryStatus(models.TextChoices):
    PENDING = "pending", "Pendente"
    SHIPPED = "shipped", "Enviado"
    DELIVERED = "delivered", "Entregue"
    READY_FOR_PICKUP = "ready_for_pickup", "Pronto para retirada"
```

> ⚠️ `READY_FOR_PICKUP` é **exclusivo para retirada**.

---

### 10.2 Order (sem regressões)

Campos relevantes:

* `delivery_type`
* `delivery_status`
* `delivery_address` (blank para retirada)

Nenhum campo anterior foi removido ou alterado.

---

## 11. Services (Fonte da Verdade)

### 11.1 Criação de Pedido

Responsável por:

* garantir isolamento por tenant
* cliente único por telefone
* aplicar regra correta de endereço

```python
delivery_address = "" if delivery_type == DeliveryType.PICKUP else data.get("delivery_address", "")
```

---

### 11.2 Mudança de Status

#### Enviar pedido

* permitido apenas para `delivery`

#### Entregar pedido

* permitido apenas após `shipped`

#### Liberar retirada

* permitido apenas para `pickup`
* altera:

  * `delivery_status → READY_FOR_PICKUP`
  * `order_status → CONFIRMED`

---

## 12. Views

* Views são **burra por definição**
* Nenhuma regra de negócio
* Apenas:

  * busca
  * delega para service
  * redireciona

Todas as actions estão cobertas:

* criar pedido
* enviar
* entregar
* liberar retirada
* imprimir etiqueta

---

## 13. URLs

Rotas disponíveis:

* `/orders/` → lista
* `/orders/novo/` → criação
* `/orders/<id>/enviar/`
* `/orders/<id>/entregar/`
* `/orders/<id>/retirada/`
* `/orders/<id>/etiqueta/`

---

## 14. Templates

### 14.1 Lista de Pedidos

* diferencia Entrega x Retirada
* botões condicionais
* botão de impressão sempre disponível

### 14.2 Criação de Pedido

* seleção de tipo (Entrega / Retirada)
* integração ViaCEP
* endereço oculto para retirada
* UX clara e sem inconsistências

### 14.3 Etiqueta de Pedido

* layout próprio para impressão
* informações essenciais
* status corretos

---

## 15. Estado Atual do Projeto

✔ Feature de Retirada finalizada
✔ Nenhuma regressão
✔ Domínio consistente
✔ Pronto para evoluir

---

## 16. Próximas Etapas Planejadas

1. Dashboard operacional
2. Mensagens de feedback (Django Messages)
3. Permissões por perfil
4. Testes automatizados

---

📌 **Este documento foi atualizado após a estabilização completa da feature de Retirada na Loja.**
