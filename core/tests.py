import logging
import os
import secrets
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.db.models import Sum
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import get_script_prefix, resolve, reverse, set_script_prefix
from django.utils import timezone

from .models import CatalogModel, ChatExchange, Conversation, WalletTransaction
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


class ProjectTestCase(TestCase):
    def setUp(self):
        previous_prefix = get_script_prefix()
        set_script_prefix('/')
        self.addCleanup(set_script_prefix, previous_prefix)


class AccountViewTests(ProjectTestCase):
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


@override_settings(
    FORCE_SCRIPT_NAME=None,
    STATIC_URL='static/',
    STRIP_PREFIX_FROM_REDIRECTS=False,
)
class HeaderNavigationTests(ProjectTestCase):
    def setUp(self):
        super().setUp()
        previous_prefix = get_script_prefix()
        set_script_prefix('/')
        self.addCleanup(set_script_prefix, previous_prefix)
        self.user = get_user_model().objects.get(username='demo')
        self.client.force_login(self.user)

    def test_logged_in_header_links_resolve_and_render_successful_pages(self):
        response = self.client.get(reverse('account_login'))
        routes = (
            ('chat', 'Chat'),
            ('model_picker', 'Models'),
            ('wallet_top_up', 'Top up'),
        )

        self.assertEqual(response.status_code, 200)
        for route_name, label in routes:
            with self.subTest(route=route_name):
                path = reverse(route_name)
                self.assertContains(response, f'href="{path}"')
                self.assertContains(response, label)
                page = self.client.get(path)
                self.assertEqual(page.status_code, 200)

    def test_logout_header_form_posts_to_named_route_and_redirects_to_login(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        page = client.get(reverse('account_login'))
        logout_path = reverse('account_logout')

        self.assertEqual(page.status_code, 200)
        self.assertContains(page, f'method="post" action="{logout_path}"')
        self.assertContains(page, 'name="csrfmiddlewaretoken"')

        csrf_token = client.cookies['csrftoken'].value
        response = client.post(logout_path, HTTP_X_CSRFTOKEN=csrf_token)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('account_login'))
        self.assertNotIn('_auth_user_id', client.session)

    def test_header_reversals_include_a_host_supplied_script_prefix(self):
        previous_prefix = get_script_prefix()
        set_script_prefix('/hosted')
        try:
            response = self.client.get('/accounts/login/')
            self.assertEqual(response.status_code, 200)
            for route_name in ('chat', 'model_picker', 'wallet_top_up', 'account_logout'):
                with self.subTest(route=route_name):
                    self.assertContains(response, f'"{reverse(route_name)}"')
        finally:
            set_script_prefix(previous_prefix)

    def test_force_script_name_prefixes_header_redirects_and_logout(self):
        prefix = '/mounted'
        previous_prefix = get_script_prefix()
        set_script_prefix(prefix)
        try:
            with override_settings(
                FORCE_SCRIPT_NAME=prefix,
                STATIC_URL=f'{prefix}/static/',
                STRIP_PREFIX_FROM_REDIRECTS=False,
                LOGIN_URL='account_login',
                LOGIN_REDIRECT_URL='site_root',
            ):
                page = self.client.get('/accounts/login/')
                self.assertEqual(page.status_code, 200)
                for route_name in ('chat', 'model_picker', 'wallet_top_up'):
                    self.assertContains(page, f'href="{reverse(route_name)}"')
                self.assertContains(page, f'action="{reverse("account_logout")}"')
                self.assertContains(page, f'href="{prefix}/static/core/accounts.css"')

                root = self.client.get('/')
                self.assertEqual(root['Location'], reverse('account_login'))

                guest = Client()
                protected = guest.get('/chat/')
                self.assertTrue(protected['Location'].startswith(reverse('account_login')))
                login = guest.post(
                    '/accounts/login/',
                    {'username': 'demo', 'password': 'demo12345'},
                )
                self.assertEqual(login['Location'], reverse('site_root'))

                logout_client = Client(enforce_csrf_checks=True)
                logout_client.force_login(self.user)
                logout_page = logout_client.get('/accounts/login/')
                csrf_token = logout_client.cookies['csrftoken'].value
                self.assertContains(
                    logout_page,
                    f'action="{reverse("account_logout")}"',
                )
                logout = logout_client.post(
                    '/accounts/logout/',
                    HTTP_X_CSRFTOKEN=csrf_token,
                )
                self.assertEqual(logout.status_code, 302)
                self.assertEqual(logout['Location'], reverse('account_login'))
        finally:
            set_script_prefix(previous_prefix)

    def test_redirect_prefix_is_stripped_only_when_enabled(self):
        prefix = '/mounted'
        previous_prefix = get_script_prefix()
        set_script_prefix(prefix)
        try:
            with override_settings(
                FORCE_SCRIPT_NAME=prefix,
                STATIC_URL=f'{prefix}/static/',
                STRIP_PREFIX_FROM_REDIRECTS=True,
                LOGIN_URL='account_login',
                LOGIN_REDIRECT_URL='site_root',
            ):
                header = self.client.get('/accounts/login/')
                self.assertContains(header, f'href="{reverse("chat")}"')
                self.assertContains(header, f'action="{reverse("account_logout")}"')
                self.assertContains(header, f'href="{prefix}/static/core/accounts.css"')

                root = self.client.get('/')
                self.assertEqual(root['Location'], '/accounts/login/')

                guest = Client()
                protected = guest.get('/chat/')
                self.assertTrue(protected['Location'].startswith('/accounts/login/'))
                login = guest.post(
                    '/accounts/login/',
                    {'username': 'demo', 'password': 'demo12345'},
                )
                self.assertEqual(login['Location'], '/')

                logout_client = Client(enforce_csrf_checks=True)
                logout_client.force_login(self.user)
                logout_client.get('/accounts/login/')
                csrf_token = logout_client.cookies['csrftoken'].value
                logout = logout_client.post(
                    '/accounts/logout/',
                    HTTP_X_CSRFTOKEN=csrf_token,
                )
                self.assertEqual(logout.status_code, 302)
                self.assertEqual(logout['Location'], '/accounts/login/')
        finally:
            set_script_prefix(previous_prefix)

    def test_force_script_name_environment_derives_static_and_route_prefix(self):
        env = os.environ.copy()
        env['FORCE_SCRIPT_NAME'] = '/mounted/'
        env['DJANGO_SETTINGS_MODULE'] = 'litechat.settings'
        for name in (
            'LLM_PROXY_BASE_URL',
            'OPENAI_PROXY_BASE_URL',
            'ANTHROPIC_PROXY_BASE_URL',
            'GOOGLE_PROXY_BASE_URL',
            'OPENAI_API_KEY',
            'ANTHROPIC_API_KEY',
            'GOOGLE_API_KEY',
            'LLM_PROXY_REQUEST_STYLE',
        ):
            env[name] = ''
        check = (
            'import django; django.setup(); '
            'from django.conf import settings; '
            'from django.templatetags.static import static; '
            'from django.urls import reverse; '
            'assert settings.FORCE_SCRIPT_NAME == "/mounted"; '
            'assert settings.STATIC_URL == "/mounted/static/"; '
            'assert reverse("chat") == "/mounted/chat/"; '
            'assert static("core/accounts.css") == "/mounted/static/core/accounts.css"'
        )
        result = subprocess.run(
            [sys.executable, '-c', check],
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )

        self.assertEqual(result.returncode, 0, 'FORCE_SCRIPT_NAME must prefix routes and static URLs')

    def test_unset_force_script_name_keeps_root_urls_and_static_path(self):
        previous_prefix = get_script_prefix()
        set_script_prefix('/')
        try:
            with override_settings(FORCE_SCRIPT_NAME=None, STATIC_URL='static/'):
                page = self.client.get(reverse('account_login'))
                self.assertContains(page, 'href="/chat/"')
                self.assertContains(page, 'action="/accounts/logout/"')
                self.assertContains(page, 'href="/static/core/accounts.css"')
        finally:
            set_script_prefix(previous_prefix)


class WalletTests(ProjectTestCase):
    def setUp(self):
        super().setUp()
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
        conversation = Conversation.objects.create(user=self.user, title='Wallet test')
        exchange = ChatExchange.objects.create(
            user=self.user,
            model=CatalogModel.objects.get(display_name='GPT-5.6 Luna'),
            conversation=conversation,
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
                conversation = Conversation.objects.create(
                    user=self.user,
                    title='Insufficient debit test',
                )
                exchange = ChatExchange.objects.create(
                    user=self.user,
                    model=CatalogModel.objects.get(display_name='GPT-5.6 Luna'),
                    conversation=conversation,
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


class CatalogPickerTests(ProjectTestCase):
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
class MeteredChatTests(ProjectTestCase):
    def setUp(self):
        super().setUp()
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

        exchange = ChatExchange.objects.get(user=self.user)
        self.assertRedirects(
            response,
            reverse('conversation_chat', args=(exchange.conversation_id,)),
        )
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


class ConversationBackfillMigrationTests(TransactionTestCase):
    migrate_from = ('core', '0006_chatexchange_and_more')
    migrate_to = ('core', '0009_require_conversation')

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        old_apps = executor.loader.project_state([self.migrate_from]).apps
        user_model = old_apps.get_model('auth', 'User')
        catalog_model = old_apps.get_model('core', 'CatalogModel')
        exchange_model = old_apps.get_model('core', 'ChatExchange')
        user = user_model.objects.create(username='migration-user', password='not-used')
        model = catalog_model.objects.create(
            provider='openai',
            display_name='Legacy model',
            model_id='legacy-model',
            tier='value',
            input_credits_per_1k_tokens=1,
            output_credits_per_1k_tokens=2,
            is_active=True,
        )
        self.legacy_prompts = (
            'First legacy prompt',
            'Second legacy prompt ' * 8,
        )
        self.legacy_exchange_ids = []
        for prompt in self.legacy_prompts:
            exchange = exchange_model.objects.create(
                user_id=user.pk,
                model_id=model.pk,
                prompt=prompt,
                reply='Legacy reply',
                input_tokens=4,
                output_tokens=3,
                input_tokens_estimated=True,
                output_tokens_estimated=True,
                credits_charged=1,
                mode='mock',
            )
            self.legacy_exchange_ids.append(exchange.pk)

        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        self.apps_at_target = executor.loader.project_state([self.migrate_to]).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_each_legacy_exchange_is_backfilled_into_its_own_titled_conversation(self):
        exchange_model = self.apps_at_target.get_model('core', 'ChatExchange')
        conversation_model = self.apps_at_target.get_model('core', 'Conversation')
        exchanges = [exchange_model.objects.get(pk=pk) for pk in self.legacy_exchange_ids]

        self.assertNotEqual(exchanges[0].conversation_id, exchanges[1].conversation_id)
        conversations = [
            conversation_model.objects.get(pk=exchange.conversation_id)
            for exchange in exchanges
        ]
        self.assertEqual(conversations[0].title, 'First legacy prompt')
        self.assertLessEqual(len(conversations[1].title), 80)
        self.assertTrue(conversations[1].title.endswith('...'))
        for index, (exchange, conversation) in enumerate(zip(exchanges, conversations)):
            self.assertEqual(conversation.user_id, exchange.user_id)
            self.assertEqual(conversation.last_activity_at, exchange.created_at)
            self.assertEqual(exchange.prompt, self.legacy_prompts[index])

    def test_reversing_session_migrations_keeps_legacy_exchange_content(self):
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        old_apps = executor.loader.project_state([self.migrate_from]).apps
        exchange_model = old_apps.get_model('core', 'ChatExchange')

        for index, exchange_id in enumerate(self.legacy_exchange_ids):
            exchange = exchange_model.objects.get(pk=exchange_id)
            self.assertEqual(exchange.prompt, self.legacy_prompts[index])
            self.assertEqual(exchange.reply, 'Legacy reply')


@override_settings(
    FORCE_SCRIPT_NAME=None,
    STATIC_URL='static/',
    STRIP_PREFIX_FROM_REDIRECTS=False,
    LLM_PROXY_BASE_URL='',
    OPENAI_PROXY_BASE_URL='',
    ANTHROPIC_PROXY_BASE_URL='',
    GOOGLE_PROXY_BASE_URL='',
    LLM_PROXY_REQUEST_STYLE='',
    LLM_MAX_OUTPUT_TOKENS=64,
)
class ConversationSessionTests(ProjectTestCase):
    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.get(username='demo')
        self.wallet = self.user.wallet
        self.value_model = CatalogModel.objects.get(display_name='GPT-5.6 Luna')
        self.premium_model = CatalogModel.objects.get(display_name='GPT-5.6 Sol')
        self.client.force_login(self.user)
        self.network_guard = patch(
            'requests.sessions.Session.send',
            side_effect=AssertionError('Unexpected network request in offline test.'),
        )
        self.network_guard.start()
        self.addCleanup(self.network_guard.stop)

    def start_chat(self, prompt, model=None):
        response = self.client.post(
            reverse('chat'),
            {'model': (model or self.value_model).pk, 'prompt': prompt},
        )
        self.assertEqual(response.status_code, 302)
        match = resolve(response['Location'])
        self.assertEqual(match.url_name, 'conversation_chat')
        return Conversation.objects.get(pk=match.kwargs['conversation_id'])

    def test_new_chat_get_is_empty_and_first_success_creates_truncated_title(self):
        response = self.client.get(reverse('chat'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Conversation.objects.filter(user=self.user).count(), 0)

        prompt = '  First   message\n' + ('detail ' * 20)
        conversation = self.start_chat(prompt)
        normalized = ' '.join(prompt.split())
        expected_title = normalized[:77].rstrip() + '...'
        exchange = conversation.exchanges.get()

        self.assertEqual(conversation.title, expected_title)
        self.assertLessEqual(len(conversation.title), 80)
        self.assertEqual(exchange.prompt, prompt.strip())
        self.assertEqual(exchange.user_id, conversation.user_id)
        self.assertEqual(exchange.model, self.value_model)

    def test_conversation_can_continue_with_a_different_model(self):
        conversation = self.start_chat('First message.', self.value_model)
        first_exchange = conversation.exchanges.get()
        second_prompt = 'token ' * 120

        response = self.client.post(
            reverse('conversation_chat', args=(conversation.pk,)),
            {'model': self.premium_model.pk, 'prompt': second_prompt},
        )

        self.assertRedirects(
            response,
            reverse('conversation_chat', args=(conversation.pk,)),
            fetch_redirect_response=False,
        )
        exchanges = list(conversation.exchanges.order_by('created_at', 'pk'))
        self.assertEqual(len(exchanges), 2)
        self.assertEqual(exchanges[0].pk, first_exchange.pk)
        self.assertEqual(exchanges[0].model, self.value_model)
        self.assertEqual(exchanges[1].model, self.premium_model)
        for exchange in exchanges:
            self.assertEqual(exchange.usage_transaction.exchange_id, exchange.pk)
            self.assertEqual(exchange.usage_transaction.amount, -exchange.credits_charged)
        self.assertGreater(exchanges[1].credits_charged, exchanges[0].credits_charged)

        history = self.client.get(reverse('conversation_chat', args=(conversation.pk,)))
        self.assertContains(history, 'First message.')
        self.assertContains(history, second_prompt[:80])
        self.assertContains(history, self.value_model.display_name)
        self.assertContains(history, self.premium_model.display_name)

    def test_rename_is_post_only_keeps_activity_and_survives_more_messages(self):
        conversation = self.start_chat('Original title prompt.')
        last_activity = conversation.last_activity_at
        rename_url = reverse('conversation_rename', args=(conversation.pk,))
        self.assertEqual(self.client.get(rename_url).status_code, 405)

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        detail_url = reverse('conversation_chat', args=(conversation.pk,))
        csrf_client.get(detail_url)
        csrf_token = csrf_client.cookies['csrftoken'].value
        rejected = csrf_client.post(rename_url, data={'title': 'Renamed chat'})
        self.assertEqual(rejected.status_code, 403)
        renamed = csrf_client.post(
            rename_url,
            data={'title': 'Renamed chat'},
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(renamed.status_code, 302)

        conversation.refresh_from_db()
        self.assertEqual(conversation.title, 'Renamed chat')
        self.assertEqual(conversation.last_activity_at, last_activity)
        self.client.post(
            detail_url,
            {'model': self.premium_model.pk, 'prompt': 'Continue with new model.'},
        )
        conversation.refresh_from_db()
        self.assertEqual(conversation.title, 'Renamed chat')
        self.assertEqual(conversation.exchanges.count(), 2)

    def test_sidebar_is_newest_first_and_paginated_by_twenty(self):
        now = timezone.now()
        conversations = [
            Conversation.objects.create(
                user=self.user,
                title=f'Saved chat {index:02d}',
                created_at=now - timedelta(minutes=index),
                last_activity_at=now - timedelta(minutes=index),
            )
            for index in range(21)
        ]

        first_page = self.client.get(reverse('chat'))
        page_obj = first_page.context['page_obj']
        self.assertEqual(page_obj.paginator.per_page, 20)
        self.assertEqual(len(page_obj.object_list), 20)
        self.assertEqual(page_obj.object_list[0].pk, conversations[0].pk)
        self.assertNotContains(first_page, 'Saved chat 20')
        self.assertContains(first_page, f'href="{reverse("chat")}?page=2"')

        second_page = self.client.get(reverse('chat'), {'page': 2})
        self.assertEqual(len(second_page.context['page_obj'].object_list), 1)
        self.assertContains(second_page, 'Saved chat 20')
        self.assertContains(second_page, f'href="{reverse("chat")}?page=1"')

    def test_delete_confirmation_soft_deletes_but_preserves_exchange_and_ledger(self):
        conversation = self.start_chat('A chat to archive.')
        exchange = conversation.exchanges.get()
        usage_entry = exchange.usage_transaction
        self.wallet.refresh_from_db()
        balance_before = self.wallet.balance
        delete_url = reverse('conversation_delete', args=(conversation.pk,))
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)

        confirmation = csrf_client.get(delete_url)
        self.assertEqual(confirmation.status_code, 200)
        self.assertContains(confirmation, 'Delete this chat?')
        conversation.refresh_from_db()
        self.assertIsNone(conversation.deleted_at)

        csrf_token = csrf_client.cookies['csrftoken'].value
        rejected = csrf_client.post(delete_url, data={'confirm': 'yes'})
        self.assertEqual(rejected.status_code, 403)
        invalid_confirmation = csrf_client.post(
            delete_url,
            data={'confirm': 'no', 'csrfmiddlewaretoken': csrf_token},
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(invalid_confirmation.status_code, 400)

        deleted = csrf_client.post(
            delete_url,
            data={'confirm': 'yes', 'csrfmiddlewaretoken': csrf_token},
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertRedirects(deleted, reverse('chat'), fetch_redirect_response=False)
        conversation.refresh_from_db()
        exchange.refresh_from_db()
        self.assertIsNotNone(conversation.deleted_at)
        self.assertEqual(exchange.conversation_id, conversation.pk)
        self.assertEqual(exchange.usage_transaction.pk, usage_entry.pk)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, balance_before)
        self.assertTrue(ChatExchange.objects.filter(pk=exchange.pk).exists())
        self.assertTrue(WalletTransaction.objects.filter(pk=usage_entry.pk).exists())
        self.assertEqual(csrf_client.get(reverse('conversation_chat', args=(conversation.pk,))).status_code, 404)
        self.assertContains(csrf_client.get(reverse('wallet_top_up')), '(deleted chat)')

    def test_other_users_receive_404_for_chat_rename_and_delete(self):
        conversation = self.start_chat('Private conversation title.')
        other_user = get_user_model().objects.create_user(
            username='other-session-owner',
            password='S3cure!Pass-2026',
        )
        other_client = Client()
        other_client.force_login(other_user)
        detail_url = reverse('conversation_chat', args=(conversation.pk,))
        rename_url = reverse('conversation_rename', args=(conversation.pk,))
        delete_url = reverse('conversation_delete', args=(conversation.pk,))

        self.assertEqual(other_client.get(detail_url).status_code, 404)
        self.assertEqual(
            other_client.post(
                detail_url,
                {'model': self.value_model.pk, 'prompt': 'Unauthorized message.'},
            ).status_code,
            404,
        )
        self.assertEqual(other_client.post(rename_url, {'title': 'Stolen title'}).status_code, 404)
        self.assertEqual(other_client.get(delete_url).status_code, 404)
        self.assertEqual(other_client.post(delete_url, {'confirm': 'yes'}).status_code, 404)
        self.assertFalse(ChatExchange.objects.filter(user=other_user).exists())
        self.assertIsNone(Conversation.objects.get(pk=conversation.pk).deleted_at)

    def test_session_links_and_forms_use_script_prefixed_urls(self):
        now = timezone.now()
        conversations = [
            Conversation.objects.create(
                user=self.user,
                title=f'Prefix chat {index:02d}',
                created_at=now - timedelta(minutes=index),
                last_activity_at=now - timedelta(minutes=index),
            )
            for index in range(21)
        ]
        conversation = conversations[0]
        prefix = '/mounted'
        previous_prefix = get_script_prefix()
        set_script_prefix(prefix)
        try:
            with override_settings(
                FORCE_SCRIPT_NAME=prefix,
                STATIC_URL=f'{prefix}/static/',
                STRIP_PREFIX_FROM_REDIRECTS=False,
            ):
                response = self.client.get(f'/chat/{conversation.pk}/')
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, f'href="{reverse("chat")}"')
                self.assertContains(
                    response,
                    f'href="{reverse("conversation_chat", args=(conversation.pk,))}"',
                )
                self.assertContains(
                    response,
                    f'action="{reverse("conversation_chat", args=(conversation.pk,))}"',
                )
                self.assertContains(
                    response,
                    f'action="{reverse("conversation_rename", args=(conversation.pk,))}"',
                )
                self.assertContains(
                    response,
                    f'href="{reverse("conversation_delete", args=(conversation.pk,))}"',
                )
                self.assertContains(
                    response,
                    f'href="{reverse("conversation_chat", args=(conversation.pk,))}?page=2"',
                )
                self.assertContains(response, f'href="{prefix}/static/core/accounts.css"')

                confirmation = self.client.get(f'/chat/{conversation.pk}/delete/')
                self.assertContains(
                    confirmation,
                    f'action="{reverse("conversation_delete", args=(conversation.pk,))}"',
                )
        finally:
            set_script_prefix(previous_prefix)


@override_settings(
    LLM_PROXY_BASE_URL='',
    OPENAI_PROXY_BASE_URL='',
    ANTHROPIC_PROXY_BASE_URL='',
    GOOGLE_PROXY_BASE_URL='',
    LLM_PROXY_REQUEST_STYLE='',
    LLM_MAX_OUTPUT_TOKENS=64,
)
@override_settings(
    LLM_PROXY_BASE_URL='',
    OPENAI_PROXY_BASE_URL='',
    ANTHROPIC_PROXY_BASE_URL='',
    GOOGLE_PROXY_BASE_URL='',
    LLM_PROXY_REQUEST_STYLE='',
    LLM_MAX_OUTPUT_TOKENS=64,
)
class ConversationSessionTests(ProjectTestCase):
    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.get(username='demo')
        self.wallet = self.user.wallet
        self.value_model = CatalogModel.objects.get(display_name='GPT-5.6 Luna')
        self.premium_model = CatalogModel.objects.get(display_name='GPT-5.6 Sol')
        self.client.force_login(self.user)
        self.network_guard = patch(
            'requests.sessions.Session.send',
            side_effect=AssertionError('Unexpected network request in offline test.'),
        )
        self.network_guard.start()
        self.addCleanup(self.network_guard.stop)
        self.network_guard = patch(
            'requests.sessions.Session.send',
            side_effect=AssertionError('Unexpected network request in offline test.'),
        )
        self.network_guard.start()
        self.addCleanup(self.network_guard.stop)

    def start_chat(self, prompt, model=None):
        response = self.client.post(
            reverse('chat'),
            {'model': (model or self.value_model).pk, 'prompt': prompt},
        )
        self.assertEqual(response.status_code, 302)
        conversation = Conversation.objects.get(user=self.user)
        self.assertEqual(response['Location'], reverse('conversation_chat', args=(conversation.pk,)))
        return conversation

    def test_new_chat_get_is_empty_and_first_success_creates_truncated_title(self):
        response = self.client.get(reverse('chat'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Conversation.objects.filter(user=self.user).count(), 0)

        prompt = '  First   message\n' + ('detail ' * 20)
        conversation = self.start_chat(prompt)
        normalized = ' '.join(prompt.split())
        expected_title = normalized[:77].rstrip() + '...'
        exchange = conversation.exchanges.get()

        self.assertEqual(conversation.title, expected_title)
        self.assertLessEqual(len(conversation.title), 80)
        self.assertEqual(exchange.prompt, prompt.strip())
        self.assertEqual(exchange.model, self.value_model)

    def test_conversation_can_continue_with_a_different_model(self):
        first_prompt = 'First message.'
        conversation = self.start_chat(first_prompt, self.value_model)
        first_exchange = conversation.exchanges.get()
        conversation.last_activity_at = timezone.now() - timedelta(days=1)
        conversation.save(update_fields=('last_activity_at',))
        prior_activity = conversation.last_activity_at
        second_prompt = 'token ' * 120

        response = self.client.post(
            reverse('conversation_chat', args=(conversation.pk,)),
            {'model': self.premium_model.pk, 'prompt': second_prompt},
        )

        self.assertRedirects(
            response,
            reverse('conversation_chat', args=(conversation.pk,)),
            fetch_redirect_response=False,
        )
        exchanges = list(conversation.exchanges.order_by('created_at', 'pk'))
        self.assertEqual(len(exchanges), 2)
        self.assertEqual(exchanges[0].pk, first_exchange.pk)
        self.assertEqual(exchanges[0].model, self.value_model)
        self.assertEqual(exchanges[1].model, self.premium_model)
        conversation.refresh_from_db()
        self.assertGreater(conversation.last_activity_at, prior_activity)
        for exchange in exchanges:
            self.assertEqual(exchange.usage_transaction.exchange_id, exchange.pk)
            self.assertEqual(exchange.usage_transaction.amount, -exchange.credits_charged)
        self.assertGreater(exchanges[1].credits_charged, exchanges[0].credits_charged)

        history = self.client.get(reverse('conversation_chat', args=(conversation.pk,)))
        self.assertContains(history, first_prompt)
        self.assertContains(history, second_prompt[:80])
        self.assertContains(history, self.value_model.display_name)
        self.assertContains(history, self.premium_model.display_name)

    def test_rename_is_post_only_keeps_activity_and_survives_more_messages(self):
        conversation = self.start_chat('Original title prompt.')
        last_activity = conversation.last_activity_at
        rename_url = reverse('conversation_rename', args=(conversation.pk,))

        self.assertEqual(self.client.get(rename_url).status_code, 405)

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        detail_url = reverse('conversation_chat', args=(conversation.pk,))
        csrf_client.get(detail_url)
        csrf_token = csrf_client.cookies['csrftoken'].value
        rejected = csrf_client.post(
            rename_url,
            data={'title': 'Renamed chat'},
        )
        self.assertEqual(rejected.status_code, 403)
        renamed = csrf_client.post(
            rename_url,
            data={'title': 'Renamed chat'},
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(renamed.status_code, 302)

        conversation.refresh_from_db()
        self.assertEqual(conversation.title, 'Renamed chat')
        self.assertEqual(conversation.last_activity_at, last_activity)

        self.client.post(
            detail_url,
            {'model': self.premium_model.pk, 'prompt': 'Continue with new model.'},
        )
        conversation.refresh_from_db()
        self.assertEqual(conversation.title, 'Renamed chat')
        self.assertEqual(conversation.exchanges.count(), 2)

    def test_sidebar_is_newest_first_and_paginated_by_twenty(self):
        now = timezone.now()
        conversations = [
            Conversation.objects.create(
                user=self.user,
                title=f'Saved chat {index:02d}',
                created_at=now - timedelta(minutes=index),
                last_activity_at=now - timedelta(minutes=index),
            )
            for index in range(21)
        ]

        first_page = self.client.get(reverse('chat'))
        page_obj = first_page.context['page_obj']
        self.assertEqual(page_obj.paginator.per_page, 20)
        self.assertEqual(len(page_obj.object_list), 20)
        self.assertEqual(page_obj.object_list[0].pk, conversations[0].pk)
        self.assertNotContains(first_page, 'Saved chat 20')
        self.assertContains(first_page, f'href="{reverse("chat")}?page=2"')

        second_page = self.client.get(reverse('chat'), {'page': 2})
        self.assertEqual(len(second_page.context['page_obj'].object_list), 1)
        self.assertContains(second_page, 'Saved chat 20')
        self.assertContains(second_page, f'href="{reverse("chat")}?page=1"')

    def test_delete_confirmation_soft_deletes_but_preserves_exchange_and_ledger(self):
        conversation = self.start_chat('A chat to archive.')
        exchange = conversation.exchanges.get()
        usage_entry = exchange.usage_transaction
        self.wallet.refresh_from_db()
        balance_before = self.wallet.balance
        delete_url = reverse('conversation_delete', args=(conversation.pk,))
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)

        confirmation = csrf_client.get(delete_url)
        self.assertEqual(confirmation.status_code, 200)
        self.assertContains(confirmation, 'Delete this chat?')
        conversation.refresh_from_db()
        self.assertIsNone(conversation.deleted_at)

        csrf_token = csrf_client.cookies['csrftoken'].value
        rejected = csrf_client.post(
            delete_url,
            data={'confirm': 'yes'},
        )
        self.assertEqual(rejected.status_code, 403)
        invalid_confirmation = csrf_client.post(
            delete_url,
            data={'confirm': 'no', 'csrfmiddlewaretoken': csrf_token},
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(invalid_confirmation.status_code, 400)

        deleted = csrf_client.post(
            delete_url,
            data={'confirm': 'yes', 'csrfmiddlewaretoken': csrf_token},
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertRedirects(deleted, reverse('chat'), fetch_redirect_response=False)
        conversation.refresh_from_db()
        exchange.refresh_from_db()
        self.assertIsNotNone(conversation.deleted_at)
        self.assertEqual(exchange.conversation_id, conversation.pk)
        self.assertEqual(exchange.usage_transaction.pk, usage_entry.pk)
        self.assertEqual(self.wallet.balance, balance_before)
        self.assertTrue(ChatExchange.objects.filter(pk=exchange.pk).exists())
        self.assertTrue(WalletTransaction.objects.filter(pk=usage_entry.pk).exists())
        self.assertEqual(csrf_client.get(reverse('conversation_chat', args=(conversation.pk,))).status_code, 404)
        self.assertContains(csrf_client.get(reverse('wallet_top_up')), '(deleted chat)')

    def test_other_users_receive_404_for_chat_rename_and_delete(self):
        conversation = self.start_chat('Private conversation title.')
        other_user = get_user_model().objects.create_user(
            username='other-session-owner',
            password='S3cure!Pass-2026',
        )
        other_client = Client()
        other_client.force_login(other_user)
        detail_url = reverse('conversation_chat', args=(conversation.pk,))
        rename_url = reverse('conversation_rename', args=(conversation.pk,))
        delete_url = reverse('conversation_delete', args=(conversation.pk,))

        self.assertEqual(other_client.get(detail_url).status_code, 404)
        self.assertEqual(
            other_client.post(
                detail_url,
                {'model': self.value_model.pk, 'prompt': 'Unauthorized message.'},
            ).status_code,
            404,
        )
        self.assertEqual(other_client.post(rename_url, {'title': 'Stolen title'}).status_code, 404)
        self.assertEqual(other_client.get(delete_url).status_code, 404)
        self.assertEqual(other_client.post(delete_url, {'confirm': 'yes'}).status_code, 404)
        self.assertFalse(ChatExchange.objects.filter(user=other_user).exists())
        self.assertIsNone(Conversation.objects.get(pk=conversation.pk).deleted_at)

    def test_session_links_and_forms_use_script_prefixed_urls(self):
        now = timezone.now()
        conversations = [
            Conversation.objects.create(
                user=self.user,
                title=f'Prefix chat {index:02d}',
                created_at=now - timedelta(minutes=index),
                last_activity_at=now - timedelta(minutes=index),
            )
            for index in range(21)
        ]
        conversation = conversations[0]
        prefix = '/mounted'
        previous_prefix = get_script_prefix()
        set_script_prefix(prefix)
        try:
            with override_settings(
                FORCE_SCRIPT_NAME=prefix,
                STATIC_URL=f'{prefix}/static/',
                STRIP_PREFIX_FROM_REDIRECTS=False,
            ):
                response = self.client.get(f'/chat/{conversation.pk}/')
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, f'href="{reverse("chat")}"')
                self.assertContains(
                    response,
                    f'href="{reverse("conversation_chat", args=(conversation.pk,))}"',
                )
                self.assertContains(
                    response,
                    f'action="{reverse("conversation_chat", args=(conversation.pk,))}"',
                )
                self.assertContains(
                    response,
                    f'action="{reverse("conversation_rename", args=(conversation.pk,))}"',
                )
                self.assertContains(
                    response,
                    f'href="{reverse("conversation_delete", args=(conversation.pk,))}"',
                )
                self.assertContains(
                    response,
                    f'href="{reverse("conversation_chat", args=(conversation.pk,))}?page=2"',
                )
                self.assertContains(response, f'href="{prefix}/static/core/accounts.css"')
        finally:
            set_script_prefix(previous_prefix)
