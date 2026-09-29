from itertools import groupby

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.conf import settings
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Sum
from django.db.models.functions import Abs
from django.http import HttpResponseBadRequest, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, FormView, TemplateView

from .chat_service import InsufficientPreflightCredits, create_exchange
from .forms import ChatForm, ConversationTitleForm, TopUpForm, UsageHistoryFilterForm
from .metering import estimate_request_cost
from .models import CatalogModel, ChatExchange, Conversation, WalletTransaction
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
        context['transactions'] = wallet.transactions.select_related(
            'exchange__conversation',
        )
        return context


class UsageHistoryView(LoginRequiredMixin, TemplateView):
    template_name = 'core/usage_history.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        wallet = user.wallet
        usage = WalletTransaction.objects.filter(
            wallet=wallet,
            transaction_type=WalletTransaction.Type.USAGE,
            exchange__user=user,
            exchange__conversation__user=user,
        )
        filter_form = UsageHistoryFilterForm(
            self.request.GET if self.request.GET else None,
            user=user,
        )
        filters_valid = not filter_form.is_bound or filter_form.is_valid()
        filtered_usage = usage
        if filters_valid and filter_form.is_bound:
            model = filter_form.cleaned_data['model']
            start_date = filter_form.cleaned_data['start_date']
            end_date = filter_form.cleaned_data['end_date']
            if model:
                filtered_usage = filtered_usage.filter(exchange__model=model)
            if start_date:
                filtered_usage = filtered_usage.filter(created_at__date__gte=start_date)
            if end_date:
                filtered_usage = filtered_usage.filter(created_at__date__lte=end_date)

        lifetime_total = -(usage.aggregate(total=Sum('amount'))['total'] or 0)
        filtered_total = -(filtered_usage.aggregate(total=Sum('amount'))['total'] or 0)
        entries = filtered_usage.order_by('-created_at', '-pk').select_related(
            'exchange__conversation',
            'exchange__model',
        ).annotate(credits_charged=Abs('amount'))
        context.update(
            {
                'filter_form': filter_form,
                'filter_error': filter_form.is_bound and not filters_valid,
                'filters_applied': bool(
                    filters_valid
                    and filter_form.is_bound
                    and any(filter_form.cleaned_data.values())
                ),
                'model_filter_value': (
                    filter_form.cleaned_data['model'].pk
                    if filters_valid and filter_form.is_bound and filter_form.cleaned_data['model']
                    else ''
                ),
                'start_date_filter_value': (
                    filter_form.cleaned_data['start_date'].isoformat()
                    if filters_valid and filter_form.is_bound and filter_form.cleaned_data['start_date']
                    else ''
                ),
                'end_date_filter_value': (
                    filter_form.cleaned_data['end_date'].isoformat()
                    if filters_valid and filter_form.is_bound and filter_form.cleaned_data['end_date']
                    else ''
                ),
                'lifetime_total': lifetime_total,
                'filtered_total': filtered_total,
                'page_obj': Paginator(entries, 20).get_page(self.request.GET.get('page')),
            }
        )
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

    def get_conversation(self):
        if not hasattr(self, '_conversation'):
            conversation_id = self.kwargs.get('conversation_id')
            self._conversation = None
            if conversation_id is not None:
                self._conversation = get_object_or_404(
                    Conversation.objects.filter(
                        user=self.request.user,
                        deleted_at__isnull=True,
                    ),
                    pk=conversation_id,
                )
        return self._conversation

    def form_valid(self, form):
        conversation = self.get_conversation()
        try:
            exchange = create_exchange(
                self.request.user,
                form.cleaned_data['model'],
                form.cleaned_data['prompt'],
                conversation=conversation,
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
        return redirect('conversation_chat', conversation_id=exchange.conversation_id)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        conversation = self.get_conversation()
        context['conversation'] = conversation
        context['exchanges'] = (
            conversation.exchanges.filter(
                user=self.request.user,
            ).select_related('model').order_by('created_at', 'pk')
            if conversation
            else ()
        )
        context['page_obj'] = Paginator(
            Conversation.objects.filter(
                user=self.request.user,
                deleted_at__isnull=True,
            ).order_by('-last_activity_at', '-pk'),
            20,
        ).get_page(self.request.GET.get('page'))
        return context


@login_required
def rename_conversation(request, conversation_id):
    conversation = get_object_or_404(
        Conversation.objects.filter(user=request.user, deleted_at__isnull=True),
        pk=conversation_id,
    )
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    form = ConversationTitleForm(request.POST)
    if form.is_valid():
        conversation.title = form.cleaned_data['title']
        conversation.save(update_fields=('title',))
        messages.success(request, 'Conversation renamed.')
    else:
        messages.error(request, 'Enter a non-empty title of at most 80 characters.')
    return redirect('conversation_chat', conversation_id=conversation.pk)


@login_required
def delete_conversation(request, conversation_id):
    conversation = get_object_or_404(
        Conversation.objects.filter(user=request.user, deleted_at__isnull=True),
        pk=conversation_id,
    )
    if request.method == 'GET':
        return render(
            request,
            'core/conversation_confirm_delete.html',
            {'conversation': conversation},
        )
    if request.method != 'POST':
        return HttpResponseNotAllowed(['GET', 'POST'])
    if request.POST.get('confirm') != 'yes':
        return HttpResponseBadRequest('Explicit delete confirmation is required.')

    conversation.deleted_at = timezone.now()
    conversation.save(update_fields=('deleted_at',))
    messages.success(request, 'Conversation deleted from your chat list.')
    return redirect('chat')


@require_POST
def chat_cost_estimate(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication is required.'}, status=401)

    form = ChatForm(request.POST)
    if not form.is_valid():
        return JsonResponse({'errors': form.errors.get_json_data()}, status=400)

    try:
        estimate = estimate_request_cost(
            form.cleaned_data['model'],
            form.cleaned_data['prompt'],
            settings.LLM_MAX_OUTPUT_TOKENS,
        )
    except ValueError:
        return JsonResponse({'error': 'The estimate is currently unavailable.'}, status=503)

    balance = request.user.wallet.balance
    return JsonResponse({
        **estimate,
        'balance': balance,
        'exceeds_balance': estimate['estimated_credits'] > balance,
    })
