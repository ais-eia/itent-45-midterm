from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse


class AccountViewTests(TestCase):
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
