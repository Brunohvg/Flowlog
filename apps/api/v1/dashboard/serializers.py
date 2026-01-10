"""
Serializers de Dashboard.
"""

from rest_framework import serializers


class DashboardSerializer(serializers.Serializer):
    """Estatísticas do dashboard."""
    
    orders_today = serializers.IntegerField()
    orders_pending = serializers.IntegerField()
    orders_month = serializers.IntegerField()
    revenue_today = serializers.DecimalField(max_digits=12, decimal_places=2)
    revenue_month = serializers.DecimalField(max_digits=12, decimal_places=2)
    ticket_medio = serializers.DecimalField(max_digits=10, decimal_places=2)
