# Credit Wallet Study

## Request

Give each user a credit balance displayed in the site header and a top-up page using a fake payment flow. New accounts and the demo account start with 100 credits. Record all balance changes in a timestamped ledger with an amount and a type (`signup_bonus`, `top_up`, or `usage`) so balances can be audited and future usage deductions can be performed safely. A fresh clone must receive the initial balances after `python manage.py migrate`.

## Feasibility

The project already has Django's built-in user accounts, an app-level signup view, a shared account template header, and a data migration that seeds the demo user. The existing `core` app and SQLite database can support the wallet, ledger, top-up view, and migration without adding packages or changing the user model. A follow-up migration can initialize existing users and the demo user, while new signup accounts can be initialized in the account-creation flow.

## Proposed Approach

- Add a `Wallet` model with a one-to-one relationship to the built-in user and a non-negative integer balance. Add a related ledger model with a signed integer amount, a transaction type choice, and an automatically recorded timestamp. Treat grants and top-ups as positive entries and usage deductions as negative entries.
- Keep the wallet balance as a materialized total for quick header display, and keep the ledger as the audit trail. Centralize all balance mutations in one service that updates the wallet and inserts its ledger entry in the same database transaction. Require positive amounts for grants/top-ups, negative amounts for usage, and reject any debit that would make the balance negative.
- Use a guarded database update with an `F()` expression and a balance floor for deductions rather than a Python read-modify-save. This avoids lost-update/overspend behavior; the ledger insert must roll back with the balance update if it fails. All user-creation paths in the app should use the wallet provisioning flow.
- Provision new signup users with a 100-credit `signup_bonus` as part of account creation. Add a migration after the existing demo-user migration that creates a 100-credit wallet and matching `signup_bonus` entry for every existing user without a wallet, including `demo`. Use historical models and an idempotent get-or-create pattern; do not edit already-applied migrations or depend on a committed SQLite database.
- Add a login-required top-up page with a positive whole-credit amount form and a fake confirmation action. On confirmation, add exactly the submitted amount and create a `top_up` ledger entry. Do not imply a dollar conversion, introduce prices/packages, or call a payment provider since none are specified.
- Add a wallet-balance context processor and show the balance in the shared site header for authenticated users. Make all user-facing templates inherit the shared base. Show the user's timestamped transaction history on the top-up page so ledger entries can be inspected.
- Test signup and demo initialization, correct starting balances and ledger entries, successful and invalid top-ups, usage deductions and insufficient-balance rejection, atomic balance/ledger updates, and header/history rendering. Update README and `doc/wiki/` with the wallet behavior and the fake nature of top-ups.

## Tradeoffs and Risks

- Storing a wallet balance duplicates the sum of the ledger, but avoids aggregating the full ledger every time the header renders. The mutation service must be the only path that changes balances, and tests should assert that the wallet total matches the ledger sum.
- Integer credits avoid floating-point rounding. No currency amount or credit price is specified, so the fake top-up should add a user-selected integer credit amount without inventing monetary pricing or predefined packages.
- SQLite does not provide effective row-level `select_for_update()` locking. Atomic transactions plus guarded `F()` updates are appropriate for this localhost project and prevent a deduction below zero; high-concurrency payment/accounting would require a database with stronger locking guarantees and a real payment design.
- The existing signup view is the normal app account-creation path. Any other supported path that creates users must also provision the wallet and bonus; otherwise an authenticated user could lack a wallet.
- The shared LiteChat base can show the balance on every user-facing page. Django admin uses a separate template base, so whether admin pages are included in “every page” should be made explicit during planning.

## Out of Scope

No real payment integration, currency conversion, credit pricing, purchase packages, usage charging UI, model/provider calls, or changes to the model catalog are proposed. The `usage` ledger type and safe deduction service prepare for later features but do not add chat usage behavior.
