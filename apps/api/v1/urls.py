"""
URLs da API v1.
"""

from django.urls import path, include

from rest_framework.routers import DefaultRouter

from .customers.views import CustomerViewSet
from .orders.views import OrderViewSet
from .payments.views import PaymentLinkViewSet
from .dashboard.views import DashboardView

router = DefaultRouter()
router.register(r"customers", CustomerViewSet, basename="customer")
router.register(r"orders", OrderViewSet, basename="order")
router.register(r"payment-links", PaymentLinkViewSet, basename="paymentlink")

urlpatterns = [
    path("", include(router.urls)),
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
]
