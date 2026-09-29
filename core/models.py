from django.conf import settings
from django.db import models
from django.db.models import Q


class Wallet(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='wallet',
    )
    balance = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.user} wallet ({self.balance} credits)'


class WalletTransaction(models.Model):
    class Type(models.TextChoices):
        SIGNUP_BONUS = 'signup_bonus', 'Signup bonus'
        TOP_UP = 'top_up', 'Top-up'
        USAGE = 'usage', 'Usage'

    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.CASCADE,
        related_name='transactions',
    )
    amount = models.BigIntegerField()
    transaction_type = models.CharField(max_length=20, choices=Type.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at', '-pk')
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(transaction_type__in=('signup_bonus', 'top_up'), amount__gt=0)
                    | Q(transaction_type='usage', amount__lt=0)
                ),
                name='wallet_transaction_amount_matches_type',
            ),
        ]
        indexes = [
            models.Index(
                fields=('wallet', '-created_at'),
                name='wallet_txn_wallet_created_idx',
            ),
        ]

    def __str__(self):
        return f'{self.get_transaction_type_display()}: {self.amount} credits'
