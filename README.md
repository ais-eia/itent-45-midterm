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

For hosted development environments, add the assigned hostname to the comma-separated `ALLOWED_HOSTS` setting and its full origin (including `http://` or `https://`) to `CSRF_TRUSTED_ORIGINS` in `.env`. See the commented placeholders in `.env.example`; do not commit a specific hosted hostname.

## Accounts

- Sign up at <http://localhost:8000/accounts/signup/>.
- Log in at <http://localhost:8000/accounts/login/>.
- While signed in, visit the login page and use its **Log out** button to end the session.

After running migrations, a local demo account is available with username `demo` and password `demo12345`. These public credentials are for local demonstration only; do not use them for real or deployed accounts.

## Credit Wallet

Signed-in users see their credit balance in the site header. New accounts and the demo account receive 100 credits from migrations/signup provisioning. Visit <http://localhost:8000/wallet/top-up/> to add a positive whole-number amount through a simulated top-up; no payment is taken and no currency conversion or credit price is defined. The page lists timestamped wallet transactions, including signup bonuses, top-ups, and future usage deductions.

## Model Catalog

Browse active provisional models at <http://localhost:8000/models/>. The picker groups them by provider, shows tier and input/output credit prices, and allows a temporary in-page selection; it does not make a model call or persist a preference. Staff can change availability in Django admin by editing the catalog's **Active** column. See `doc/wiki/model-catalog.md` for the provisional catalog and price ladder; its IDs and invented credit prices are not official.
