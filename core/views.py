from django.contrib import messages
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.urls import reverse_lazy
from django.views.generic import CreateView, FormView

from .forms import TopUpForm
from .models import WalletTransaction
from .wallets import apply_wallet_transaction


class SignUpView(CreateView):
    form_class = UserCreationForm
    template_name = 'core/signup.html'
    success_url = reverse_lazy('account_login')

    @transaction.atomic
    def form_valid(self, form):
        return super().form_valid(form)


class WalletTopUpView(LoginRequiredMixin, FormView):
    form_class = TopUpForm
    template_name = 'core/wallet_top_up.html'
    success_url = reverse_lazy('wallet_top_up')

    def form_valid(self, form):
        amount = form.cleaned_data['amount']
        apply_wallet_transaction(
            self.request.user.wallet,
            amount,
            WalletTransaction.Type.TOP_UP,
        )
        messages.success(self.request, f'{amount} credits added with a fake payment.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        wallet = self.request.user.wallet
        context['wallet'] = wallet
        context['transactions'] = wallet.transactions.all()
        return context
