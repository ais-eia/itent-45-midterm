# LiteChat Midterm Project

## Requirements

- Python 3.12.3

## Setup and Run

From a fresh clone, run these commands from the repository root:

```sh
python3.12 -m venv env
source env/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver
```

The development server is available at <http://localhost:8000/>; the site root redirects to the login page.

`.env.example` contains placeholders for local development. Replace them in your local `.env` as needed; never commit `.env` or real provider credentials.

For hosted development environments, add the assigned hostname (without a scheme or path) to `ALLOWED_HOSTS` and its full origin (scheme plus hostname, without a path prefix) to `CSRF_TRUSTED_ORIGINS` in `.env`. If the host mounts the app under a path prefix and does not pass WSGI `SCRIPT_NAME`, set `FORCE_SCRIPT_NAME` to that prefix so Django reversals and static URLs stay under the mount. If the host also prepends that same prefix to response `Location` headers, enable `STRIP_PREFIX_FROM_REDIRECTS`; leave it off otherwise. See the commented placeholders in `.env.example`; do not commit a specific hosted hostname.

## Hosted Preview Navigation

The signed-in header links and logout action use named Django routes. If a hosted preview shows a navigation or method error and no matching request appears in the `runserver` terminal, the request is being handled or misrouted before it reaches Django. Check that the preview preserves the app's origin/path prefix and forwards both GET and POST requests; for a path-mounted WSGI deployment, the host must provide the correct `SCRIPT_NAME` or configure `FORCE_SCRIPT_NAME`. A direct curl POST without a browser session's CSRF cookie/token is expected to receive HTTP 403.

## Accounts

- Sign up at <http://localhost:8000/accounts/signup/>.
- Log in at <http://localhost:8000/accounts/login/>.
- While signed in, visit the login page and use its **Log out** button to end the session.

After running migrations, a local demo account is available with username `demo` and password `demo12345`. These public credentials are for local demonstration only; do not use them for real or deployed accounts.

## Credit Wallet

Signed-in users see their credit balance in the site header. New accounts and the demo account receive 100 credits from migrations/signup provisioning. Visit <http://localhost:8000/wallet/top-up/> to add a positive whole-number amount through a simulated top-up; no payment is taken and no currency conversion or credit price is defined. The page lists timestamped wallet transactions, including signup bonuses, top-ups, and future usage deductions.

## Model Catalog

Browse active provisional models at <http://localhost:8000/models/>. The picker groups them by provider, shows tier and input/output credit prices, and allows a temporary in-page selection; it does not make a model call or persist a preference. Staff can change availability in Django admin by editing the catalog's **Active** column. See `doc/wiki/model-catalog.md` for the provisional catalog and price ladder; its IDs and invented credit prices are not official.

## Metered Chat

After logging in, open <http://localhost:8000/chat/> to choose an active model and send a prompt. Each successful exchange and its credit cost appear below the chat form.

When no applicable proxy endpoint is configured, the app uses MOCK. If an endpoint is configured, the app requires the selected provider's environment credential and `LLM_PROXY_REQUEST_STYLE` (`openai_compatible` or `provider_native`); missing configuration or a failed request returns an error and never falls back to MOCK. Configure `LLM_PROXY_BASE_URL` or a provider-specific `OPENAI_PROXY_BASE_URL`, `ANTHROPIC_PROXY_BASE_URL`, or `GOOGLE_PROXY_BASE_URL` override, the corresponding `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `GOOGLE_API_KEY`, and `LLM_MAX_OUTPUT_TOKENS` in your local `.env`. The proxy request contract is not confirmed. Never commit, print, or log credential values or proxy endpoint values.

Chat pre-checks affordability using an estimate and does not reserve credits. After a successful reply, it records the exchange and usage debit atomically. If the balance changes before the debit and is then insufficient, the reply is discarded with no charge and the user is asked to retry; the provider may still have incurred cost. Configured proxy failures show an error, never fall back to MOCK, and are not charged.
