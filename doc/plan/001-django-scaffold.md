# Django Scaffold Plan

- [x] Review the existing repository and confirm the named unused scaffolds are untracked before removing them.
- [x] Remove only untracked `config/`, `chat/`, `manage.py`, and `requirements.txt`; confirm `db.sqlite3` is absent.
- [x] Record feasibility, approach, tradeoffs, and scope in `doc/study/001-django-scaffold.md`.
- [x] Create and work on a new branch for the scaffold.
- [x] Install Django and python-dotenv in the existing `./env` and generate `requirements.txt` from the environment.
- [x] Run `django-admin startproject litechat .` and `python manage.py startapp core`.
- [x] Register `core` and configure `SECRET_KEY` and `DEBUG` through python-dotenv with safe development fallbacks.
- [x] Add `.env.example` with placeholders for `SECRET_KEY`, `DEBUG`, `LLM_PROXY_BASE_URL`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, and `GOOGLE_API_KEY`.
- [x] Add `README.md` with Python 3.12.3 and exact fresh-clone setup and run steps.
- [x] Run migrations and verify the default Django welcome page at `http://localhost:8000` with a background server that is stopped afterward.
- [ ] Review the diff, commit in Conventional Commit chunks, verify a fresh clone according to `AGENTS.md` where applicable, merge to `main`, and try pushing to `origin main`.
- [x] Update `doc/wiki/` to reflect the scaffolded project.
