from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils import timezone


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
    exchange = models.OneToOneField(
        'ChatExchange',
        on_delete=models.PROTECT,
        related_name='usage_transaction',
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at', '-pk')
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(
                        transaction_type__in=('signup_bonus', 'top_up'),
                        amount__gt=0,
                        exchange__isnull=True,
                    )
                    | Q(
                        transaction_type='usage',
                        amount__lt=0,
                        exchange__isnull=False,
                    )
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


class CatalogModel(models.Model):
    class Provider(models.TextChoices):
        OPENAI = 'openai', 'OpenAI'
        ANTHROPIC = 'anthropic', 'Anthropic'
        GOOGLE = 'google', 'Google'

    class Tier(models.TextChoices):
        VALUE = 'value', 'Value'
        STANDARD = 'standard', 'Standard'
        PREMIUM = 'premium', 'Premium'

    provider = models.CharField(max_length=16, choices=Provider.choices)
    display_name = models.CharField(max_length=100)
    model_id = models.CharField(max_length=100)
    tier = models.CharField(max_length=16, choices=Tier.choices)
    input_credits_per_1k_tokens = models.PositiveIntegerField()
    output_credits_per_1k_tokens = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ('provider', 'tier', 'display_name')
        constraints = [
            models.UniqueConstraint(
                fields=('provider', 'model_id'),
                name='catalog_provider_model_id_unique',
            ),
            models.CheckConstraint(
                condition=(
                    Q(provider__in=('openai', 'anthropic', 'google'))
                    & Q(tier__in=('value', 'standard', 'premium'))
                    & Q(input_credits_per_1k_tokens__gt=0)
                    & Q(output_credits_per_1k_tokens__gt=0)
                ),
                name='catalog_provider_tier_prices_valid',
            ),
        ]

    def __str__(self):
        return f'{self.display_name} ({self.get_provider_display()})'


class ChatExchange(models.Model):
    class Mode(models.TextChoices):
        MOCK = 'mock', 'Mock'
        REAL = 'real', 'Real'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='chat_exchanges',
    )
    model = models.ForeignKey(
        CatalogModel,
        on_delete=models.PROTECT,
        related_name='exchanges',
    )
    conversation = models.ForeignKey(
        'Conversation',
        on_delete=models.PROTECT,
        related_name='exchanges',
    )
    prompt = models.TextField()
    reply = models.TextField()
    input_tokens = models.PositiveIntegerField()
    output_tokens = models.PositiveIntegerField()
    input_tokens_estimated = models.BooleanField(default=False)
    output_tokens_estimated = models.BooleanField(default=False)
    credits_charged = models.PositiveBigIntegerField()
    mode = models.CharField(max_length=8, choices=Mode.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at', '-pk')

    def __str__(self):
        return f'{self.user} - {self.model.display_name} ({self.credits_charged} credits)'


class Conversation(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='conversations',
    )
    title = models.CharField(max_length=80)
    created_at = models.DateTimeField(default=timezone.now)
    last_activity_at = models.DateTimeField(default=timezone.now)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ('-last_activity_at', '-pk')
        indexes = [
            models.Index(
                fields=('user', '-last_activity_at'),
                name='conversation_user_activity_idx',
            ),
        ]

    def __str__(self):
        return self.title
