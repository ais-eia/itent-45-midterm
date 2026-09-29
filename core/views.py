from itertools import groupby

from django.contrib import messages
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.urls import reverse_lazy
from django.views.generic import CreateView, FormView, TemplateView

from .chat_service import InsufficientPreflightCredits, create_exchange
from .forms import ChatForm, TopUpForm
from .models import CatalogModel, ChatExchange, WalletTransaction
from .providers import ProviderError
from .wallets import InsufficientCredits, apply_wallet_transaction


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


class CatalogPickerView(TemplateView):
    template_name = 'core/model_picker.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        models = list(
            CatalogModel.objects.filter(is_active=True).order_by(
                'provider',
                'tier',
                'display_name',
            )
        )
        provider_labels = dict(CatalogModel.Provider.choices)
        context['provider_groups'] = [
            {'provider': provider_labels[provider], 'models': list(group)}
            for provider, group in groupby(models, key=lambda model: model.provider)
        ]
        selected_id = self.request.GET.get('selected')
        context['selected_model'] = next(
            (model for model in models if str(model.pk) == selected_id),
            None,
        )
        return context


class ChatView(LoginRequiredMixin, FormView):
    form_class = ChatForm
    template_name = 'core/chat.html'
    success_url = reverse_lazy('chat')

    def form_valid(self, form):
        try:
            create_exchange(
                self.request.user,
                form.cleaned_data['model'],
                form.cleaned_data['prompt'],
            )
        except InsufficientPreflightCredits:
            form.add_error(
                None,
                'Your balance is too low for the estimated cost of this request. Top up and retry.',
            )
            return self.form_invalid(form)
        except InsufficientCredits:
            form.add_error(
                None,
                'Your balance changed while the reply was generated. The reply was discarded and nothing was charged; please retry.',
            )
            return self.form_invalid(form)
        except ProviderError as error:
            form.add_error(None, str(error))
            return self.form_invalid(form)
        except Exception:
            form.add_error(None, 'The reply could not be saved or charged. Nothing was charged; please retry.')
            return self.form_invalid(form)
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['exchanges'] = ChatExchange.objects.filter(
            user=self.request.user,
        ).select_related('model')
        return context
