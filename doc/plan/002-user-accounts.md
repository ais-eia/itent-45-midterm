# User Accounts Plan

- [x] Confirm the approved scope in `doc/study/002-user-accounts.md`.
- [x] Create a new feature branch for user accounts.
- [x] Add `core` account URLs under `/accounts/` with stable names: `account_signup`, `account_login`, and `account_logout`.
- [x] Implement signup with Django's `UserCreationForm`; on success, redirect to the named login page.
- [x] Configure Django's built-in `LoginView` with `AuthenticationForm`, preserve safe `next` redirects, and use `/` as the fallback destination because no app landing page exists yet.
- [x] Route `/` to the login page so the planned post-login fallback remains usable after configuring account URLs.
- [x] Configure Django's built-in `LogoutView` for CSRF-protected POST requests and redirect to the named login page.
- [x] Add simple signup and login templates with CSRF tokens, validation errors, and links between the account routes; provide logout as a POST form for authenticated users.
- [x] Add an idempotent `RunPython` data migration in `core` that depends on the configured user model and creates `demo` with password `demo12345` only when that username is absent; store the password hashed through Django.
- [x] Add tests for signup success and validation failure, login success and invalid credentials, safe `next` handling, POST logout/session clearing, CSRF protection, and demo account authentication after migrations.
- [x] Update `README.md` with the account URLs and local-only demo credentials; update `doc/wiki/` with the account flows and seed behavior.
- [x] Run Django checks and tests, then verify migrations and demo login from a fresh Django test database.
- [x] Clone into `/tmp`, follow only the README setup, confirm migrations and server startup, and verify `demo` / `demo12345` login; remove the temporary clone.
- [x] Review and commit changes using Conventional Commits.
- [x] Merge the branch to `main`, confirm the app runs after merge, and push to `origin main`.

Out of scope: custom user model, email verification, password reset, profile fields, roles, billing, chat, provider calls, and model catalog changes.
