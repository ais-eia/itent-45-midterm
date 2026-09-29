# Project Setup

- The project uses Python 3.12.3, Django 6.1.1, and SQLite.
- `manage.py` is at the repository root. Django settings and URL configuration are in `litechat/`; the initial `core` app is registered in settings.
- The local database is `db.sqlite3` and is intentionally ignored by Git. Apply Django migrations with `python manage.py migrate` after cloning; migrations also seed the demo user and its initial wallet ledger entry.
- `litechat/settings.py` loads the root `.env` with python-dotenv. `SECRET_KEY` and `DEBUG` can be overridden through environment variables; safe development-only defaults allow the scaffold to start without `.env`.
- `.env.example` documents the expected local Django and provider/proxy variable names with blank proxy/key values. Signup, login, logout, the demo account, credit wallet, provisional model catalog, and metered chat are implemented. REAL proxy compatibility remains unverified until its request contract is known.
- Follow `README.md` for the exact virtual environment, dependency installation, environment-file, migration, and server commands.
