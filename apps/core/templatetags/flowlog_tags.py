"""
Template tags customizadas do Flowlog.
"""

from django import template
from decimal import Decimal

register = template.Library()


@register.filter
def currency(value):
    """
    Formata valor como moeda brasileira.
    Ex: 1234.56 -> 1.234,56
    """
    if value is None:
        return "0,00"
    
    try:
        value = Decimal(str(value))
        formatted = "{:,.2f}".format(value)
        # Trocar . por X, depois , por . e X por ,
        formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
        return formatted
    except (ValueError, TypeError):
        return "0,00"


@register.filter
def phone_link(value):
    """
    Formata número de telefone para link do WhatsApp.
    Remove caracteres não numéricos.
    """
    if not value:
        return ""
    
    return ''.join(filter(str.isdigit, str(value)))


@register.simple_tag
def query_string(request, **kwargs):
    """
    Atualiza a query string mantendo parâmetros existentes.
    Uso: {% query_string request page=2 %}
    """
    query = request.GET.copy()
    for key, value in kwargs.items():
        if value:
            query[key] = value
        elif key in query:
            del query[key]
    return query.urlencode()
