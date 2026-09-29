# User Accounts

- Accounts use Django's built-in `User` model and authentication views. Signup uses `UserCreationForm`, including Django's configured password validation and password hashing.
- Signup, login, and logout routes are `/accounts/signup/`, `/accounts/login/`, and `/accounts/logout/` respectively.
- Logout is a CSRF-protected POST form. Login honors Django's validated `next` destination and otherwise redirects to `/`, which forwards to the login/account page.
- The `core.0001_seed_demo_user` data migration creates the `demo` user with password `demo12345` only if the username is not already present. Django stores a password hash, not the plain-text password.
- The demo credentials are intentionally public and local-only. They are not suitable for real accounts or a deployed service. On a database that already has a `demo` username, the migration leaves its existing password unchanged.
- Follow `README.md` for local setup and the demo credentials. Email verification, password reset, profile fields, and custom account roles are not implemented.
