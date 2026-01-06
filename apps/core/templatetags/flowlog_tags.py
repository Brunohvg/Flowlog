"""
Template tags customizadas do Flowlog.
"""

from decimal import InvalidOperation

from django import template

register = template.Library()


@register.filter
def currency(value):
    """
    Formata valor como moeda brasileira.
    Ex: 1234.56 -> 1.234,56
    Blinda contra None, strings vazias e erros de conversão decimal.
    """
    # 1. Tratamento explícito de vazio
    if value is None or value == "":
        return "0,00"

    try:
        # 2. Convertemos para float primeiro (mais tolerante que Decimal para display)
        # Se preferires Decimal, funciona igual desde que tenhas o InvalidOperation no except
        val = float(value)

        # 3. Formatação usando f-string (mais rápida e limpa)
        formatted = f"{val:,.2f}"

        # 4. Troca de pontuação (US -> BR)
        return formatted.replace(",", "X").replace(".", ",").replace("X", ".")

    except (ValueError, TypeError, InvalidOperation):
        # Se qualquer coisa der errado, devolve 0,00 em vez de quebrar a página
        return "0,00"


@register.filter
def phone_link(value):
    """
    Formata número de telefone para link do WhatsApp.
    Remove caracteres não numéricos.
    """
    if not value:
        return ""

    return "".join(filter(str.isdigit, str(value)))


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
