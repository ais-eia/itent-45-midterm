# Hosted Development

- The account, chat, model, and wallet header actions are generated with Django named URL reversals; logout is a CSRF-protected POST form.
- Run `python manage.py test core.tests.HeaderNavigationTests` to verify the signed-in Chat, Models, and Top up destinations return HTTP 200, generated routes honor Django's active script prefix, and logout redirects back to login.
- A browser error with no corresponding request in the Django `runserver` terminal indicates the preview/browser/proxy handled or misrouted the request before it reached the app. Check the preview origin, path prefix, and forwarding of both GET and POST methods. For a path-mounted deployment, the host should pass `SCRIPT_NAME`; if it cannot, set `FORCE_SCRIPT_NAME` to the mount prefix so Django reversals, redirects, and static URLs include it.
- `ALLOWED_HOSTS` contains hostnames only. `CSRF_TRUSTED_ORIGINS` contains the matching scheme and hostname, not the path prefix. Keep the path prefix in `FORCE_SCRIPT_NAME` only.
- A direct curl POST to logout without a browser session's CSRF cookie/token should receive HTTP 403; this is expected CSRF protection, not an unsupported-method response.
