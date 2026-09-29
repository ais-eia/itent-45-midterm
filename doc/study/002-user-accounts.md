# User Accounts Study

## Request

Add user signup, login, and logout using Django's built-in authentication, and seed a demo account (`demo` / `demo12345`) with a data migration so a fresh database has working demo credentials after `python manage.py migrate`.

## Feasibility

This is a small, self-contained feature for the current project. Django's `auth`, `sessions`, and `contenttypes` apps are already installed, and the authentication, session, and CSRF middleware are enabled. The existing `core` app can own account URLs, views, forms, templates, and the data migration. SQLite and the current pinned dependencies are sufficient; no additional packages or custom user model are needed.

## Proposed Approach

- Use Django's built-in `User` model. Use `UserCreationForm` for signup so Django's configured password validation and password hashing apply, and use Django's `AuthenticationForm` and auth views/utilities for login and session handling.
- Provide simple Django-template pages for signup and login, with CSRF tokens on forms. Make logout a CSRF-protected POST action rather than a state-changing GET request.
- Keep account routing under a clear `/accounts/` URL prefix with stable named routes. Honor Django's `next` redirect for protected destinations and define an explicit safe fallback for successful login/logout; the current root still shows Django's welcome page and no product landing page is in scope.
- Add a `RunPython` data migration in `core` that depends on the swappable user model and creates the `demo` account with a Django password hash. Use historical migration models and the migration database alias. Create the user only when absent so applying the seed does not reset an existing account's password. The migration should be safe on a fresh database and should not depend on `db.sqlite3` being committed.
- Add focused tests for successful and invalid signup/login, logout behavior, the seeded user's ability to authenticate, and the demo account's presence after migrations. Update README and the project wiki with account flows and the public demo credentials.

## Tradeoffs and Security

- Reusing Django auth avoids duplicating password storage, session management, password validation, and authentication logic. The default username-based account model is sufficient for the requested feature; email verification, password reset, profile fields, and role/permission design are not included.
- The requested demo password must appear as seed input in migration code, but the database should store only Django's password hash. These credentials are intentionally public and suitable only for local/demo use; they must not be presented as secure credentials for real accounts or a deployed service.
- Creating the demo user only when missing avoids overwriting an existing `demo` account. As a result, an already-populated database containing a different `demo` user will retain its existing password; fresh clones receive the requested credentials deterministically.
- Django's `LoginView` and `LogoutView` keep the implementation small, while signup needs a small custom view to create the user and choose its post-registration redirect. A login landing target must be made explicit because the project does not yet have an application home page.

## Verification Considerations

- Confirm migration ordering works from an empty SQLite database and that running migrations leaves the demo account usable.
- Exercise the signup, login, and POST logout flows with Django's test client, including invalid credentials and CSRF protection behavior.
- Before merging, follow only the README setup in a fresh `/tmp` clone, confirm migrations and the server work, and verify login using `demo` / `demo12345`.

## Out of Scope

No custom user model, email confirmation, password reset, user profile, authorization roles, billing, chat, provider integration, or changes to the model catalog are proposed here.
