# Credit Wallet Plan

- [x] Confirm the approved scope and design in `doc/study/003-credit-wallet.md`.
- [x] Create a new feature branch for the credit wallet.
- [x] Add a `Wallet` model with one wallet per user and a non-negative integer balance.
- [x] Add a related ledger model with signed integer `amount`, `signup_bonus` / `top_up` / `usage` type, and timestamp; add database constraints that reject zero amounts and enforce positive grant/top-up and negative usage signs.
- [x] Add migrations after the existing demo-user migration to create the wallet/ledger schema and backfill each existing user, including `demo`, with balance 100 and one `signup_bonus` ledger entry. Use historical models and idempotent creation.
- [x] Add a centralized wallet service that updates the materialized balance and writes the matching ledger entry atomically; use guarded `F()` updates for debits, reject balances below zero, and prevent direct balance changes outside this service.
- [x] Integrate wallet provisioning into signup so each new user gets a 100-credit balance and exactly one `signup_bonus` entry in the same atomic account-creation operation.
- [x] Add an authenticated top-up page at `/wallet/top-up/` with a CSRF-protected form for a positive whole-credit amount and a clearly fake confirmation; successful top-ups must call the wallet service and create a positive `top_up` entry without a monetary conversion or real payment call.
- [x] Show the user's timestamped ledger history on the top-up page.
- [x] Add a wallet-balance context processor and show the current balance in the shared header on every user-facing LiteChat page, including account and top-up pages.
- [x] Add tests for migration/signup/demo starting balances, ledger-to-balance consistency, successful and invalid top-ups, anonymous access, signed usage deductions, insufficient-balance rejection, atomic rollback, and balance/history header rendering.
- [x] Update `README.md` and `doc/wiki/` with the wallet header, fake top-up flow, ledger semantics, and 100-credit starting bonus.
- [x] Run Django checks/tests and verify a fresh database migration initializes the demo wallet and ledger correctly.
- [ ] Clone into `/tmp`, follow only the README setup, confirm migrations and server startup, test demo login and wallet balance/top-up, then remove the temporary clone.
- [ ] Review and commit with Conventional Commits, merge to `main`, confirm the app works after merge, and push to `origin main`.

## Scope Decision For Review

The header checklist covers all user-facing LiteChat pages. Django's built-in admin UI is not included in that shared site-header scope unless explicitly requested.

The fake top-up accepts an integer credit amount only; no currency pricing, bundles, or real payment behavior is introduced. The `usage` ledger type and safe debit service do not add model usage charging.
