# Credit Wallet

- Each built-in user has one `Wallet` with a non-negative integer balance. `WalletTransaction` is the audit ledger, with a signed integer amount, transaction type, and creation timestamp.
- `signup_bonus` and `top_up` entries are positive credits; `usage` entries are negative debits. A database constraint enforces these signs. Wallet totals are updated only through `core.wallets.apply_wallet_transaction()`, which applies the balance change and inserts the ledger record in one transaction.
- Debit updates use a guarded `F()` expression so a balance cannot fall below zero. The service raises `InsufficientCredits` without recording a transaction when funds are insufficient.
- The migration after the demo-user seed creates a 100-credit wallet and `signup_bonus` ledger entry for every existing user without a wallet. Newly created users are provisioned through the user-created signal. Signup and top-up changes are atomic.
- Authenticated users see their balance and a top-up link in the shared LiteChat header. The top-up page is `/wallet/top-up/`; it accepts a positive integer credit amount, simulates confirmation without taking payment, and lists the user's timestamped ledger history.
- There is no credit-to-currency rate, pricing, or real payment integration. The `usage` type and safe debit service are available for later features but do not charge chat usage yet.
