# Project Workflow

Follow this workflow for every feature or change:

1. **Study**: Analyze the request, feasibility, approach, and tradeoffs. Write a Markdown study at `doc/study/NNN-short-slug.md`. Do not write or change code during this step.
2. **Plan**: Based on the study, write a Markdown checklist with concrete steps at `doc/plan/NNN-short-slug.md`. Use the same numeric prefix and slug as the study.
3. **Execute plan**: Create a new Git branch for the work. Implement the plan and tick checklist items off as they are completed. Keep changes scoped to the approved plan.
4. **Rendezvous**: Once the branch works, verify it using a fresh clone as described below, merge it back into `main`, and confirm the app still runs after the merge.
5. **Sync docs**: Update `doc/wiki/` after implementation so it reflects the current codebase.

## Repository Rules

- Use Conventional Commits for all commits, including prefixes such as `feat:`, `fix:`, `chore:`, `build:`, `docs:`, `refactor:`, and `test:`.
- Never commit secrets or the virtual environment. Local secrets belong in `.env`; `.env.example` documents required variables with placeholder values.
- Keep the repository self-sufficient. After every change, keep `requirements.txt`, `.env.example`, and `README.md` (including exact setup and run steps) up to date. A fresh clone must run after: create a virtual environment, `pip install -r requirements.txt`, `cp .env.example .env`, `python manage.py migrate`, and `python manage.py runserver`.
- Always commit database migrations. Never add migrations to `.gitignore`. Since `db.sqlite3` is not committed, create seed data (including the model catalog and demo user) with a data migration or management command.
- Do not use hardcoded absolute paths or put secrets in code.
- Before merging any branch, clone the repository into `/tmp`, follow only the README steps, confirm migrations run and the server starts, then delete the temporary clone. Once the user accounts feature exists, also confirm the demo login works.
- Name study and plan files with a numeric prefix and slug, for example `doc/study/001-user-accounts.md` and `doc/plan/001-user-accounts.md`.

## Project Scope

- Use Django with SQLite, Django templates, and simple CSS. Do not add a frontend build step.
- Providers in scope are OpenAI, Anthropic, and Google. Every model belongs to one tier: `value`, `standard`, or `premium`.
- `doc/wiki/model-catalog.md` is the source of truth for the model catalog. Do not invent models or prices.
- Real LLM requests go through a proxy whose base URL is configured with `LLM_PROXY_BASE_URL`. Provider credentials come from `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, and `GOOGLE_API_KEY` in the environment. If the required keys are missing, the app must run in a clearly labeled mock mode.
