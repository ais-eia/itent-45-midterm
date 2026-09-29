# Django Scaffold Study

## Request

Replace the unused untracked default Django scaffold with a root-level `litechat` Django project and a registered `core` app. Configure Django and python-dotenv, add environment-backed development settings, document exact clone setup and run steps, migrate the database, and verify Django's default welcome page on localhost.

## Feasibility

The repository has no tracked application scaffold. The previously present untracked `config/`, `chat/`, `manage.py`, and `requirements.txt` were explicitly identified as unused and removed. `db.sqlite3` was absent. Python 3.12.3, Django 6.1.1, and python-dotenv 1.2.3 are available in the existing `./env` virtual environment, so the project can be generated without changing the repository's Python runtime.

## Approach

- Generate the Django project in the repository root using `django-admin startproject litechat .`, then generate the `core` app using the root `manage.py`.
- Register `core` in `INSTALLED_APPS` and use python-dotenv to load `.env` values from the project root. Read `SECRET_KEY` and `DEBUG` from the environment with a clearly development-only fallback secret and debug default.
- Keep the existing SQLite and Django template defaults; do not introduce a frontend build step or implement product features.
- Add a placeholder `.env.example` covering the requested Django and LLM proxy/provider variables, plus a README with Python version and the exact fresh-clone setup and run commands.
- Run migrations and a non-blocking local HTTP check of Django's default welcome page, then stop the server.

## Tradeoffs

- Pin the installed Django and python-dotenv versions in `requirements.txt` so setup is reproducible in the requested Python 3.12 environment.
- A safe local fallback makes the scaffold runnable even if `.env` is missing, while `.env.example` remains the documented setup path. The fallback is not suitable for deployment and should not be treated as a secret.
- Keep the generated `litechat` package name aligned with the requested command rather than retaining or renaming the discarded `config` package.

## Out of Scope

No chat, account, billing, model catalog, provider integration, mock LLM behavior, or demo login is implemented as part of this scaffold.
