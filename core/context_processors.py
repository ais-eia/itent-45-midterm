from .models import Wallet


def wallet_balance(request):
    if not request.user.is_authenticated:
        return {'wallet_balance': None}
    try:
        balance = request.user.wallet.balance
    except Wallet.DoesNotExist:
        balance = None
    return {'wallet_balance': balance}
