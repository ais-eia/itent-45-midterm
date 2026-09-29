import logging
import os
import secrets
from unittest.mock import Mock, patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import CatalogModel, ChatExchange, WalletTransaction
from .metering import credits_for_usage, estimate_tokens
from .providers import (
    MockBackend,
    ProxyBackend,
    get_backend,
)
from .wallets import InsufficientCredits, apply_wallet_transaction, provision_wallet


class CapturingHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


class AccountViewTests(TestCase):
    def test_root_redirects_to_account_login(self):
        response = self.client.get('/')

        self.assertRedirects(response, reverse('account_login'))

    def test_signup_creates_user_and_redirects_to_login(self):
        response = self.client.post(
            reverse('account_signup'),
            {
                'username': 'newuser',
                'password1': 'S3cure!Pass-2026',
                'password2': 'S3cure!Pass-2026',
            },
        )

        self.assertRedirects(
            response,
            reverse('account_login'),
            fetch_redirect_response=False,
        )
        user = get_user_model().objects.get(username='newuser')
        self.assertTrue(user.check_password('S3cure!Pass-2026'))
        self.assertEqual(user.wallet.balance, 100)
        bonus = user.wallet.transactions.get()
        self.assertEqual(bonus.amount, 100)
        self.assertEqual(bonus.transaction_type, WalletTransaction.Type.SIGNUP_BONUS)

    def test_signup_rejects_mismatched_passwords(self):
        response = self.client.post(
            reverse('account_signup'),
            {
                'username': 'newuser',
                'password1': 'S3cure!Pass-2026',
                'password2': 'different-password',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(get_user_model().objects.filter(username='newuser').exists())

    def test_demo_user_is_seeded_and_can_log_in(self):
        user = get_user_model().objects.get(username='demo')
        self.assertTrue(user.check_password('demo12345'))
        self.assertEqual(user.wallet.balance, 100)
        bonus = user.wallet.transactions.get()
        self.assertEqual(bonus.amount, 100)
        self.assertEqual(bonus.transaction_type, WalletTransaction.Type.SIGNUP_BONUS)

        response = self.client.post(
            reverse('account_login'),
            {'username': 'demo', 'password': 'demo12345'},
        )

        self.assertRedirects(response, '/', fetch_redirect_response=False)
        self.assertEqual(self.client.session['_auth_user_id'], str(user.pk))

    def test_login_rejects_invalid_credentials(self):
        response = self.client.post(
            reverse('account_login'),
            {'username': 'demo', 'password': 'incorrect'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_login_honors_safe_next_destination(self):
        response = self.client.post(
            reverse('account_login'),
            {
                'username': 'demo',
                'password': 'demo12345',
                'next': '/accounts/signup/',
            },
        )

        self.assertRedirects(
            response,
            reverse('account_signup'),
            fetch_redirect_response=False,
        )

    def test_login_rejects_external_next_destination(self):
        response = self.client.post(
            reverse('account_login'),
            {
                'username': 'demo',
                'password': 'demo12345',
                'next': 'https://outside.example/',
            },
        )

        self.assertRedirects(response, '/', fetch_redirect_response=False)

    def test_logout_is_post_only_and_clears_session(self):
        user = get_user_model().objects.create_user(
            username='logout-user',
            password='S3cure!Pass-2026',
        )
        self.client.force_login(user)

        get_response = self.client.get(reverse('account_logout'))
        self.assertEqual(get_response.status_code, 405)

        response = self.client.post(reverse('account_logout'))
        self.assertRedirects(
            response,
            reverse('account_login'),
            fetch_redirect_response=False,
        )
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_logout_requires_csrf_token(self):
        user = get_user_model().objects.create_user(
            username='csrf-user',
            password='S3cure!Pass-2026',
        )
        client = Client(enforce_csrf_checks=True)
        client.force_login(user)

        logout_url = reverse('account_logout')
        rejected = client.post(logout_url)
        self.assertEqual(rejected.status_code, 403)

        client.get(reverse('account_login'))
        csrf_token = client.cookies['csrftoken'].value
        accepted = client.post(logout_url, HTTP_X_CSRFTOKEN=csrf_token)
        self.assertRedirects(
            accepted,
            reverse('account_login'),
            fetch_redirect_response=False,
        )
        self.assertNotIn('_auth_user_id', client.session)


class WalletTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.get(username='demo')
        self.wallet = self.user.wallet
        self.client.force_login(self.user)

    def test_new_users_receive_one_starting_bonus(self):
        user = get_user_model().objects.create_user(
            username='wallet-user',
            password='S3cure!Pass-2026',
        )

        self.assertEqual(user.wallet.balance, 100)
        bonus = user.wallet.transactions.get()
        self.assertEqual(bonus.amount, 100)
        self.assertEqual(bonus.transaction_type, WalletTransaction.Type.SIGNUP_BONUS)
        provision_wallet(user)
        self.assertEqual(user.wallet.transactions.count(), 1)

    def test_authenticated_user_sees_balance_and_top_up_history(self):
        response = self.client.get(reverse('account_login'))
        self.assertContains(response, '100 credits')

        response = self.client.get(reverse('wallet_top_up'))
        self.assertContains(response, 'Current balance:')
        self.assertContains(response, 'Signup bonus')
        self.assertContains(response, '100 credits')

    def test_anonymous_user_cannot_open_top_up_page(self):
        self.client.logout()

        response = self.client.get(reverse('wallet_top_up'))

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse('account_login')))

    def test_fake_top_up_updates_balance_and_records_ledger(self):
        response = self.client.post(
            reverse('wallet_top_up'),
            {'amount': '25'},
            follow=True,
        )

        self.assertRedirects(response, reverse('wallet_top_up'))
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 125)
        top_up = self.wallet.transactions.first()
        self.assertEqual(top_up.amount, 25)
        self.assertEqual(top_up.transaction_type, WalletTransaction.Type.TOP_UP)
        self.assertEqual(
            self.wallet.transactions.aggregate(total=Sum('amount'))['total'],
            self.wallet.balance,
        )
        self.assertContains(response, 'fake payment')

    def test_invalid_top_up_amounts_do_not_change_wallet(self):
        for amount in ('0', '-5', 'not-a-number'):
            with self.subTest(amount=amount):
                response = self.client.post(reverse('wallet_top_up'), {'amount': amount})
                self.assertEqual(response.status_code, 200)
                self.wallet.refresh_from_db()
                self.assertEqual(self.wallet.balance, 100)
                self.assertEqual(self.wallet.transactions.count(), 1)

    def test_usage_debit_records_negative_amount(self):
        exchange = ChatExchange.objects.create(
            user=self.user,
            model=CatalogModel.objects.get(display_name='GPT-5.6 Luna'),
            prompt='test prompt',
            reply='test reply',
            input_tokens=1,
            output_tokens=1,
            credits_charged=35,
            mode=ChatExchange.Mode.MOCK,
        )
        entry = apply_wallet_transaction(
            self.wallet,
            -35,
            WalletTransaction.Type.USAGE,
            exchange=exchange,
        )

        self.wallet.refresh_from_db()
        self.assertEqual(entry.amount, -35)
        self.assertEqual(self.wallet.balance, 65)
        self.assertEqual(
            self.wallet.transactions.aggregate(total=Sum('amount'))['total'],
            self.wallet.balance,
        )

    def test_insufficient_usage_debit_changes_nothing(self):
        with self.assertRaises(InsufficientCredits):
            with transaction.atomic():
                exchange = ChatExchange.objects.create(
                    user=self.user,
                    model=CatalogModel.objects.get(display_name='GPT-5.6 Luna'),
                    prompt='test prompt',
                    reply='test reply',
                    input_tokens=1,
                    output_tokens=1,
                    credits_charged=101,
                    mode=ChatExchange.Mode.MOCK,
                )
                apply_wallet_transaction(
                    self.wallet,
                    -101,
                    WalletTransaction.Type.USAGE,
                    exchange=exchange,
                )

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 100)
        self.assertEqual(self.wallet.transactions.count(), 1)

    def test_service_rejects_fractional_credit_amounts(self):
        with self.assertRaises(ValueError):
            apply_wallet_transaction(
                self.wallet,
                1.5,
                WalletTransaction.Type.TOP_UP,
            )

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 100)
        self.assertEqual(self.wallet.transactions.count(), 1)

    def test_ledger_failure_rolls_back_balance_update(self):
        with patch(
            'core.wallets.WalletTransaction.objects.create',
            side_effect=RuntimeError('ledger insert failed'),
        ):
            with self.assertRaisesMessage(RuntimeError, 'ledger insert failed'):
                apply_wallet_transaction(
                    self.wallet,
                    25,
                    WalletTransaction.Type.TOP_UP,
                )

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 100)
        self.assertEqual(self.wallet.transactions.count(), 1)

    def test_database_constraint_rejects_invalid_transaction_sign(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            WalletTransaction.objects.create(
                wallet=self.wallet,
                amount=-1,
                transaction_type=WalletTransaction.Type.TOP_UP,
            )


class CatalogPickerTests(TestCase):
    def test_provisional_catalog_seed_has_all_nine_expected_models(self):
        expected = {
            ('openai', 'gpt-5.6-luna'): ('GPT-5.6 Luna', 'value', 1, 2),
            ('openai', 'gpt-5.6-terra'): ('GPT-5.6 Terra', 'standard', 3, 6),
            ('openai', 'gpt-5.6-sol'): ('GPT-5.6 Sol', 'premium', 9, 18),
            ('anthropic', 'claude-haiku-4.5'): ('Claude Haiku 4.5', 'value', 1, 2),
            ('anthropic', 'claude-sonnet-5.5'): ('Claude Sonnet 5.5', 'standard', 3, 6),
            ('anthropic', 'claude-opus-5.5'): ('Claude Opus 5.5', 'premium', 9, 18),
            ('google', 'gemini-3.1-flash-lite'): ('Gemini 3.1 Flash-Lite', 'value', 1, 2),
            ('google', 'gemini-3.8-flash'): ('Gemini 3.8 Flash', 'standard', 3, 6),
            ('google', 'gemini-3.1-pro'): ('Gemini 3.1 Pro', 'premium', 9, 18),
        }
        actual = {
            (model.provider, model.model_id): (
                model.display_name,
                model.tier,
                model.input_credits_per_1k_tokens,
                model.output_credits_per_1k_tokens,
            )
            for model in CatalogModel.objects.all()
        }

        self.assertEqual(actual, expected)
        self.assertEqual(CatalogModel.objects.filter(is_active=True).count(), 9)

    def test_catalog_constraints_enforce_supported_values_and_unique_ids(self):
        invalid_rows = (
            {'provider': 'other'},
            {'tier': 'ultra'},
            {'input_credits_per_1k_tokens': 0},
            {'output_credits_per_1k_tokens': 0},
        )
        for index, overrides in enumerate(invalid_rows):
            row = {
                'provider': 'openai',
                'display_name': f'Invalid {index}',
                'model_id': f'invalid-{index}',
                'tier': 'value',
                'input_credits_per_1k_tokens': 1,
                'output_credits_per_1k_tokens': 2,
            }
            row.update(overrides)
            with self.subTest(overrides=overrides):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    CatalogModel.objects.create(**row)

        existing = CatalogModel.objects.get(provider='openai', model_id='gpt-5.6-luna')
        with self.assertRaises(IntegrityError), transaction.atomic():
            CatalogModel.objects.create(
                provider=existing.provider,
                display_name='Duplicate ID',
                model_id=existing.model_id,
                tier='value',
                input_credits_per_1k_tokens=1,
                output_credits_per_1k_tokens=2,
            )

        cross_provider = CatalogModel.objects.create(
            provider='anthropic',
            display_name='Provider-scoped ID',
            model_id=existing.model_id,
            tier='value',
            input_credits_per_1k_tokens=1,
            output_credits_per_1k_tokens=2,
        )
        self.assertEqual(cross_provider.provider, 'anthropic')

    def test_picker_groups_active_models_and_selection_is_not_persisted(self):
        demo_wallet = get_user_model().objects.get(username='demo').wallet
        balance_before = demo_wallet.balance
        transactions_before = demo_wallet.transactions.count()
        inactive = CatalogModel.objects.get(display_name='GPT-5.6 Sol')
        inactive.is_active = False
        inactive.save(update_fields=('is_active',))

        response = self.client.get(reverse('model_picker'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'OpenAI')
        self.assertContains(response, 'Anthropic')
        self.assertContains(response, 'Google')
        self.assertContains(response, 'GPT-5.6 Luna')
        self.assertContains(response, 'credits / 1k')
        self.assertNotContains(response, 'GPT-5.6 Sol')

        selected = CatalogModel.objects.get(display_name='GPT-5.6 Terra')
        response = self.client.get(reverse('model_picker'), {'selected': selected.pk})
        self.assertContains(response, 'Selected:')
        self.assertContains(response, 'GPT-5.6 Terra')
        self.assertNotIn('selected', self.client.session)
        demo_wallet.refresh_from_db()
        self.assertEqual(demo_wallet.balance, balance_before)
        self.assertEqual(demo_wallet.transactions.count(), transactions_before)

    def test_inactive_models_cannot_be_selected(self):
        model = CatalogModel.objects.get(display_name='GPT-5.6 Luna')
        model.is_active = False
        model.save(update_fields=('is_active',))

        response = self.client.get(reverse('model_picker'), {'selected': model.pk})

        self.assertNotContains(response, 'Selected:')
        self.assertNotContains(response, 'GPT-5.6 Luna')

    @patch('requests.sessions.Session.request')
    def test_picker_does_not_make_provider_requests(self, provider_request):
        response = self.client.get(reverse('model_picker'))

        self.assertEqual(response.status_code, 200)
        provider_request.assert_not_called()

    def test_admin_uses_list_editable_active_flag(self):
        staff = get_user_model().objects.create_superuser(
            username='catalog-staff',
            email='catalog-staff@example.invalid',
            password='S3cure!Pass-2026',
        )
        self.client.force_login(staff)
        model_admin = admin.site._registry[CatalogModel]
        self.assertIn('is_active', model_admin.list_display)
        self.assertIn('is_active', model_admin.list_editable)

        changelist_url = reverse('admin:core_catalogmodel_changelist')
        response = self.client.get(changelist_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="form-0-is_active"')

        models = list(CatalogModel.objects.order_by('provider', 'tier', 'display_name'))
        target = models[0]
        form_data = {
            'form-TOTAL_FORMS': str(len(models)),
            'form-INITIAL_FORMS': str(len(models)),
            'form-MIN_NUM_FORMS': '0',
            'form-MAX_NUM_FORMS': '1000',
            '_save': 'Save',
        }
        for index, model in enumerate(models):
            form_data[f'form-{index}-id'] = str(model.pk)
            if model.pk != target.pk:
                form_data[f'form-{index}-is_active'] = 'on'

        response = self.client.post(changelist_url, form_data)

        self.assertEqual(response.status_code, 302)
        target.refresh_from_db()
        self.assertFalse(target.is_active)


@override_settings(
    LLM_PROXY_BASE_URL='',
    OPENAI_PROXY_BASE_URL='',
    ANTHROPIC_PROXY_BASE_URL='',
    GOOGLE_PROXY_BASE_URL='',
    LLM_PROXY_REQUEST_STYLE='',
    LLM_MAX_OUTPUT_TOKENS=64,
)
class MeteredChatTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.get(username='demo')
        self.wallet = self.user.wallet
        self.model = CatalogModel.objects.get(display_name='GPT-5.6 Luna')
        self.client.force_login(self.user)
        self.network_guard = patch(
            'requests.sessions.Session.send',
            side_effect=AssertionError('Unexpected network request in offline test.'),
        )
        self.network_guard.start()
        self.addCleanup(self.network_guard.stop)

    def test_unconfigured_proxy_uses_mock_even_if_provider_key_exists(self):
        sentinel = secrets.token_urlsafe(24)
        with patch.dict(os.environ, {'OPENAI_API_KEY': sentinel}):
            backend = get_backend(self.model)

        self.assertIsInstance(backend, MockBackend)

    def test_mock_reply_is_labeled_metered_and_linked_to_usage(self):
        prompt = 'Explain token metering.'
        response = self.client.post(
            reverse('chat'),
            {'model': self.model.pk, 'prompt': prompt},
            follow=True,
        )

        self.assertRedirects(response, reverse('chat'))
        exchange = ChatExchange.objects.get(user=self.user)
        self.assertEqual(exchange.mode, ChatExchange.Mode.MOCK)
        self.assertIn('MOCK MODE', exchange.reply)
        self.assertTrue(exchange.input_tokens_estimated)
        self.assertTrue(exchange.output_tokens_estimated)
        self.assertEqual(exchange.input_tokens, estimate_tokens(prompt))
        self.assertEqual(exchange.output_tokens, estimate_tokens(exchange.reply))
        self.assertContains(response, 'MOCK REPLY - SIMULATED')
        self.assertContains(response, f'{exchange.credits_charged} credits charged')

        debit = exchange.usage_transaction
        self.assertEqual(debit.transaction_type, WalletTransaction.Type.USAGE)
        self.assertEqual(debit.exchange_id, exchange.pk)
        self.assertEqual(debit.amount, -exchange.credits_charged)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 100 - exchange.credits_charged)

    def test_preflight_blocks_without_calling_backend(self):
        self.wallet.balance = 0
        self.wallet.save(update_fields=('balance',))

        with patch('core.chat_service.get_backend') as backend_factory:
            response = self.client.post(
                reverse('chat'),
                {'model': self.model.pk, 'prompt': 'A message.'},
            )

        backend_factory.assert_not_called()
        self.assertContains(response, 'balance is too low')
        self.assertFalse(ChatExchange.objects.filter(user=self.user).exists())
        self.assertEqual(self.wallet.transactions.count(), 1)

    def test_inactive_model_is_rejected(self):
        inactive = CatalogModel.objects.get(display_name='GPT-5.6 Terra')
        inactive.is_active = False
        inactive.save(update_fields=('is_active',))

        with patch('core.chat_service.get_backend') as backend_factory:
            response = self.client.post(
                reverse('chat'),
                {'model': inactive.pk, 'prompt': 'A message.'},
            )

        backend_factory.assert_not_called()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ChatExchange.objects.filter(user=self.user).exists())

    def test_charge_rounds_combined_cost_up_once(self):
        self.assertEqual(credits_for_usage(self.model, 1000, 1000), 3)
        self.assertEqual(credits_for_usage(self.model, 499, 1), 1)
        self.assertEqual(credits_for_usage(self.model, 500, 1), 1)
        self.assertEqual(credits_for_usage(self.model, 998, 1), 1)
        self.assertEqual(credits_for_usage(self.model, 999, 1), 2)

    def test_real_usage_counts_are_stored_and_charged(self):
        sentinel = secrets.token_urlsafe(24)
        response_body = {
            'choices': [{'message': {'content': 'A real-style reply.'}}],
            'usage': {'prompt_tokens': 100, 'completion_tokens': 30},
        }
        response = Mock(status_code=200)
        response.json.return_value = response_body

        with override_settings(
            OPENAI_PROXY_BASE_URL=object(),
            LLM_PROXY_REQUEST_STYLE='openai_compatible',
        ):
            with patch.dict(os.environ, {'OPENAI_API_KEY': sentinel}):
                with patch('core.providers.requests.post', return_value=response):
                    result = self.client.post(
                        reverse('chat'),
                        {'model': self.model.pk, 'prompt': 'A prompt.'},
                        follow=True,
                    )

        exchange = ChatExchange.objects.get(user=self.user)
        self.assertEqual(exchange.mode, ChatExchange.Mode.REAL)
        self.assertEqual(exchange.reply, 'A real-style reply.')
        self.assertEqual((exchange.input_tokens, exchange.output_tokens), (100, 30))
        self.assertFalse(exchange.input_tokens_estimated)
        self.assertFalse(exchange.output_tokens_estimated)
        expected_charge = credits_for_usage(self.model, 100, 30)
        self.assertEqual(exchange.credits_charged, expected_charge)
        self.assertEqual(exchange.usage_transaction.amount, -expected_charge)
        self.assertContains(result, 'REAL REPLY')

    def test_provider_native_response_usage_is_normalized(self):
        cases = (
            (
                'anthropic',
                {'content': [{'type': 'text', 'text': 'Native reply.'}], 'usage': {'input_tokens': 12, 'output_tokens': 8}},
                'Claude Haiku 4.5',
            ),
            (
                'google',
                {'candidates': [{'content': {'parts': [{'text': 'Native reply.'}]}}], 'usageMetadata': {'promptTokenCount': 12, 'candidatesTokenCount': 8}},
                'Gemini 3.1 Flash-Lite',
            ),
        )
        for provider, body, display_name in cases:
            with self.subTest(provider=provider):
                model = CatalogModel.objects.get(display_name=display_name)
                response = Mock(status_code=200)
                response.json.return_value = body
                backend = ProxyBackend(
                    object(),
                    provider,
                    model.model_id,
                    'provider_native',
                    secrets.token_urlsafe(24),
                )
                with patch('core.providers.requests.post', return_value=response) as outbound:
                    result = backend.complete(model, 'A prompt.', 64)
                self.assertEqual(result.reply, 'Native reply.')
                self.assertEqual((result.input_tokens, result.output_tokens), (12, 8))
                self.assertEqual(outbound.call_args.kwargs['json']['model'], model.model_id)

    def test_configured_proxy_without_key_errors_without_mock_fallback(self):
        with override_settings(
            OPENAI_PROXY_BASE_URL=object(),
            LLM_PROXY_REQUEST_STYLE='openai_compatible',
        ):
            with patch.dict(os.environ, {'OPENAI_API_KEY': ''}):
                with patch('core.providers.requests.post') as outbound:
                    response = self.client.post(
                        reverse('chat'),
                        {'model': self.model.pk, 'prompt': 'A message.'},
                    )

        outbound.assert_not_called()
        self.assertContains(response, 'credential is required')
        self.assertNotContains(response, 'MOCK MODE')
        self.assertFalse(ChatExchange.objects.filter(user=self.user).exists())

    def test_configured_proxy_without_style_errors_without_mock_fallback(self):
        with override_settings(
            OPENAI_PROXY_BASE_URL=object(),
            LLM_PROXY_REQUEST_STYLE='',
        ):
            with patch.dict(os.environ, {'OPENAI_API_KEY': secrets.token_urlsafe(24)}):
                with patch('core.providers.requests.post') as outbound:
                    response = self.client.post(
                        reverse('chat'),
                        {'model': self.model.pk, 'prompt': 'A message.'},
                    )

        outbound.assert_not_called()
        self.assertContains(response, 'request style is missing or unsupported')
        self.assertNotContains(response, 'MOCK MODE')
        self.assertFalse(ChatExchange.objects.filter(user=self.user).exists())

    def test_failed_proxy_call_does_not_fall_back_or_charge(self):
        with override_settings(
            OPENAI_PROXY_BASE_URL=object(),
            LLM_PROXY_REQUEST_STYLE='openai_compatible',
        ):
            with patch.dict(os.environ, {'OPENAI_API_KEY': secrets.token_urlsafe(24)}):
                with patch(
                    'core.providers.requests.post',
                    side_effect=RuntimeError('opaque transport failure'),
                ) as outbound:
                    response = self.client.post(
                        reverse('chat'),
                        {'model': self.model.pk, 'prompt': 'A message.'},
                    )

        self.assertTrue(outbound.called)
        self.assertContains(response, 'configured model proxy could not be reached')
        self.assertNotContains(response, 'MOCK MODE')
        self.assertFalse(ChatExchange.objects.filter(user=self.user).exists())
        self.assertEqual(self.wallet.transactions.count(), 1)

    def test_proxy_key_sentinel_is_absent_from_logs_and_user_error(self):
        sentinel = secrets.token_urlsafe(32)
        root_logger = logging.getLogger()
        handler = CapturingHandler()
        root_logger.addHandler(handler)
        try:
            with override_settings(
                OPENAI_PROXY_BASE_URL=object(),
                LLM_PROXY_REQUEST_STYLE='openai_compatible',
            ):
                with patch.dict(os.environ, {'OPENAI_API_KEY': sentinel}):
                    with patch(
                        'core.providers.requests.post',
                        side_effect=RuntimeError(f'transport error {sentinel}'),
                    ):
                        response = self.client.post(
                            reverse('chat'),
                            {'model': self.model.pk, 'prompt': 'A message.'},
                        )
        finally:
            root_logger.removeHandler(handler)

        response_text = response.content.decode()
        logged_text = '\n'.join(handler.messages)
        self.assertFalse(
            sentinel in response_text or sentinel in logged_text,
            'Sensitive data escaped into output.',
        )

    def test_final_debit_failure_discards_reply_and_exchange(self):
        transactions_before = self.wallet.transactions.count()
        with patch(
            'core.chat_service.apply_wallet_transaction',
            side_effect=InsufficientCredits('balance changed'),
        ):
            response = self.client.post(
                reverse('chat'),
                {'model': self.model.pk, 'prompt': 'A message.'},
            )

        self.assertContains(response, 'reply was discarded')
        self.assertFalse(ChatExchange.objects.filter(user=self.user).exists())
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 100)
        self.assertEqual(self.wallet.transactions.count(), transactions_before)
