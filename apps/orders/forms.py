from django import forms


class OrderCreateForm(forms.Form):
    customer_name = forms.CharField(label="Nome do Cliente", max_length=200)
    customer_phone = forms.CharField(label="Telefone", max_length=20)
    total_value = forms.DecimalField(
        label="Valor Total", max_digits=10, decimal_places=2
    )
    delivery_address = forms.CharField(
        label="Endereço", widget=forms.Textarea, required=False
    )
    notes = forms.CharField(label="Observações", widget=forms.Textarea, required=False)
