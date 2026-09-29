from django.urls import path

from .views import WalletTopUpView

urlpatterns = [
    path('top-up/', WalletTopUpView.as_view(), name='wallet_top_up'),
]
