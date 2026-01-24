"""
Forms do app orders - Flowlog.
"""

import re
from decimal import Decimal, InvalidOperation

from django import forms
from django.utils import timezone

from apps.orders.models import DeliveryType


class BrazilianDecimalField(forms.DecimalField):
    """Campo decimal que aceita formato brasileiro (vírgula como separador)."""

    def to_python(self, value):
        if value in self.empty_values:
            return None

        # Remove pontos de milhar e troca vírgula por ponto
        if isinstance(value, str):
            value = value.strip()
            # Remove R$ se presente
            value = re.sub(r"^R\$\s*", "", value)
            # Remove pontos de milhar (1.234,56 -> 1234,56)
            value = value.replace(".", "")
            # Troca vírgula por ponto (1234,56 -> 1234.56)
            value = value.replace(",", ".")

        try:
            return Decimal(value)
        except (InvalidOperation, ValueError):
            raise forms.ValidationError("Digite um valor válido.")


class OrderCreateForm(forms.Form):
    """Formulário para criar pedido."""

    customer_name = forms.CharField(
        label="Nome do Cliente",
        max_length=200,
    )
    customer_phone = forms.CharField(
        label="Telefone",
        max_length=20,
    )
    customer_cpf = forms.CharField(
        label="CPF",
        max_length=14,
        required=False,
        help_text="Usado para acompanhamento do pedido",
    )
    total_value = BrazilianDecimalField(
        label="Valor Total",
        max_digits=10,
        decimal_places=2,
    )
    sale_date = forms.DateField(
        label="Data da Venda",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Deixe em branco para usar a data de hoje",
    )
    delivery_type = forms.ChoiceField(
        label="Tipo de Entrega",
        choices=DeliveryType.choices,
        initial=DeliveryType.MOTOBOY,
    )
    delivery_address = forms.CharField(
        label="Endereço", required=False, widget=forms.Textarea(attrs={"rows": 3})
    )
    notes = forms.CharField(
        label="Observações", required=False, widget=forms.Textarea(attrs={"rows": 2})
    )

    # Campos Motoboy
    motoboy_fee = BrazilianDecimalField(
        label="Valor Motoboy",
        max_digits=10,
        decimal_places=2,
        required=False,
        help_text="Taxa paga ao motoboy pela entrega",
    )
    motoboy_paid = forms.BooleanField(
        label="Motoboy já foi pago?",
        required=False,
        initial=False,
    )

    def clean_customer_cpf(self):
        cpf = self.cleaned_data.get("customer_cpf", "")
        if cpf:
            # Remove formatação
            cpf_digits = "".join(filter(str.isdigit, cpf))
            if cpf_digits and len(cpf_digits) != 11:
                raise forms.ValidationError("CPF deve ter 11 dígitos.")
        return cpf

    def clean_sale_date(self):
        sale_date = self.cleaned_data.get("sale_date")
        if sale_date:
            today = timezone.now().date()
            if sale_date > today:
                raise forms.ValidationError("Data da venda não pode ser futura.")
        return sale_date

    def clean(self):
        cleaned_data = super().clean()
        delivery_type = cleaned_data.get("delivery_type")
        delivery_address = cleaned_data.get("delivery_address")

        # Endereço obrigatório para entregas
        if DeliveryType.requires_address(delivery_type):
            if not delivery_address or not delivery_address.strip():
                raise forms.ValidationError(
                    "Endereço de entrega é obrigatório para este tipo de envio."
                )

        return cleaned_data


class OrderShipForm(forms.Form):
    """Formulário para marcar pedido como enviado."""

    tracking_code = forms.CharField(
        label="Código de Rastreio",
        max_length=50,
        required=False,
    )

    def __init__(self, *args, order=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.order = order

        # Se é Correios, tracking é obrigatório
        if order and DeliveryType.requires_tracking(order.delivery_type):
            self.fields["tracking_code"].required = True

    def clean_tracking_code(self):
        tracking_code = self.cleaned_data.get("tracking_code")

        if self.order and DeliveryType.requires_tracking(self.order.delivery_type):
            if not tracking_code or not tracking_code.strip():
                raise forms.ValidationError(
                    f"Código de rastreio é obrigatório para {self.order.get_delivery_type_display()}."
                )

        if tracking_code:
            return tracking_code.strip().upper()

        return tracking_code


class OrderCancelForm(forms.Form):
    """Formulário para cancelar pedido."""

    reason = forms.CharField(
        label="Motivo do Cancelamento",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )


class TrackingSearchForm(forms.Form):
    """Formulário para buscar pedido para acompanhamento."""

    search = forms.CharField(
        label="Buscar", max_length=20, help_text="Digite o código do pedido ou CPF"
    )
