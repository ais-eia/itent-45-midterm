from django.urls import path

from .views import UsageHistoryView, WalletTopUpView

urlpatterns = [
    path('top-up/', WalletTopUpView.as_view(), name='wallet_top_up'),
    path('usage/', UsageHistoryView.as_view(), name='usage_history'),
]
