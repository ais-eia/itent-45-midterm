from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .metering import credits_for_usage, estimate_tokens
from .models import CatalogModel, ChatExchange, Conversation, WalletTransaction
from .providers import ProviderError, get_backend
from .wallets import InsufficientCredits, apply_wallet_transaction


class InsufficientPreflightCredits(Exception):
    pass


def title_from_prompt(prompt):
    title = ' '.join(prompt.split())
    if len(title) > 80:
        return title[:77].rstrip() + '...'
    return title


def create_exchange(user, model, prompt, conversation=None):
    if not CatalogModel.objects.filter(pk=model.pk, is_active=True).exists():
        raise ProviderError('The selected model is no longer active. Please choose another model.')
    if conversation is not None:
        conversation = Conversation.objects.filter(
            pk=conversation.pk,
            user=user,
            deleted_at__isnull=True,
        ).first()
        if conversation is None:
            raise ProviderError('This conversation is unavailable.')

    max_output_tokens = settings.LLM_MAX_OUTPUT_TOKENS
    if max_output_tokens < 1:
        raise ProviderError('The configured output-token limit is invalid.')

    wallet = user.wallet
    estimated_input_tokens = estimate_tokens(prompt)
    preflight_credits = credits_for_usage(
        model,
        estimated_input_tokens,
        max_output_tokens,
    )
    if wallet.balance < preflight_credits:
        raise InsufficientPreflightCredits

    backend = get_backend(model)
    result = backend.complete(model, prompt, max_output_tokens)
    input_tokens_estimated = result.input_tokens is None or result.input_tokens == 0
    output_tokens_estimated = result.output_tokens is None
    input_tokens = (
        estimate_tokens(prompt)
        if input_tokens_estimated
        else result.input_tokens
    )
    output_tokens = (
        estimate_tokens(result.reply)
        if output_tokens_estimated
        else result.output_tokens
    )
    credits_charged = credits_for_usage(model, input_tokens, output_tokens)

    with transaction.atomic():
        if conversation is None:
            conversation = Conversation.objects.create(
                user=user,
                title=title_from_prompt(prompt),
                last_activity_at=timezone.now(),
            )
        else:
            conversation_updates = {'last_activity_at': timezone.now()}
            if not conversation.title:
                conversation_updates['title'] = title_from_prompt(prompt)
            updated = Conversation.objects.filter(
                pk=conversation.pk,
                user=user,
                deleted_at__isnull=True,
            ).update(**conversation_updates)
            if updated != 1:
                raise ProviderError('This conversation is unavailable.')

        exchange = ChatExchange.objects.create(
            user=user,
            model=model,
            conversation=conversation,
            prompt=prompt,
            reply=result.reply,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            input_tokens_estimated=input_tokens_estimated,
            output_tokens_estimated=output_tokens_estimated,
            credits_charged=credits_charged,
            mode=result.mode,
        )
        apply_wallet_transaction(
            wallet,
            -credits_charged,
            WalletTransaction.Type.USAGE,
            exchange=exchange,
        )
    return exchange
