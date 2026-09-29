from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import Wallet, WalletTransaction

STARTING_CREDITS = 100


class InsufficientCredits(Exception):
    pass


@transaction.atomic
def apply_wallet_transaction(wallet, amount, transaction_type):
    if not isinstance(amount, int) or isinstance(amount, bool):
        raise ValueError('Wallet amounts must be whole credits.')
    if transaction_type in (WalletTransaction.Type.SIGNUP_BONUS, WalletTransaction.Type.TOP_UP):
        if amount <= 0:
            raise ValueError('Credit grants must be positive.')
    elif transaction_type == WalletTransaction.Type.USAGE:
        if amount >= 0:
            raise ValueError('Usage transactions must be negative.')
    else:
        raise ValueError('Unknown wallet transaction type.')

    wallets = Wallet.objects.filter(pk=wallet.pk)
    if amount < 0:
        wallets = wallets.filter(balance__gte=-amount)
    updated = wallets.update(
        balance=F('balance') + amount,
        updated_at=timezone.now(),
    )
    if updated != 1:
        if not Wallet.objects.filter(pk=wallet.pk).exists():
            raise Wallet.DoesNotExist
        raise InsufficientCredits('The wallet does not have enough credits.')

    entry = WalletTransaction.objects.create(
        wallet_id=wallet.pk,
        amount=amount,
        transaction_type=transaction_type,
    )
    wallet.refresh_from_db(fields=('balance', 'updated_at'))
    return entry


@transaction.atomic
def provision_wallet(user):
    wallet, created = Wallet.objects.get_or_create(user=user)
    if created:
        apply_wallet_transaction(
            wallet,
            STARTING_CREDITS,
            WalletTransaction.Type.SIGNUP_BONUS,
        )
    return wallet
