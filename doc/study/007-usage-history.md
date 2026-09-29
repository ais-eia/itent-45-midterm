# Usage History Study

## Request

Give each signed-in user a newest-first, 20-per-page history of every charged chat exchange. Rows must show the charge timestamp, chat title (append `(deleted chat)` for a soft-deleted conversation), model and tier, input/output tokens, credits charged, and MOCK/REAL mode. Include credits spent and filters by model and date range. The displayed total must reconcile with that user's usage transactions, including transactions for deleted chats. Keep all reads private to the signed-in user and keep tests offline in MOCK mode.

## Existing Implementation

- `WalletTransaction` is already the authoritative audit ledger. A `usage` row has a negative `amount`, a wallet, a creation timestamp, and a protected one-to-one link to its `ChatExchange`; a database constraint requires the link and negative amount. Signup grants and top-ups are positive and must not be included in usage totals.
- `ChatExchange` holds the model, input/output token counts, mode (`mock` or `real`), and `credits_charged`. It belongs to both a user and a conversation. `Conversation` supplies the title and soft-delete timestamp.
- `/wallet/top-up/` already lists the signed-in user's wallet transactions and labels a usage entry `(deleted chat)` when its conversation was soft-deleted. The view selects the exchange and conversation, but the table only shows transaction type, signed amount, and timestamp; it has no usage-specific filters or total.
- `core/wallet_urls.py` currently routes to the top-up page only. No separate usage-history page or usage-history storage model exists.

## Proposed Approach

- Add a read-only usage-history page backed directly by `WalletTransaction` usage rows. Keep the general wallet transaction history and its existing deleted-chat marker; do not copy usage data into a new table or calculate the page from `ChatExchange` alone. Add a link from the wallet page and a named route, proposed as `/wallet/usage/`.
- Build the base queryset from `request.user.wallet` and `transaction_type=usage`; also constrain the linked exchange and conversation to `request.user` as defense in depth. Do not exclude rows based on `Conversation.deleted_at`; instead, show the retained title with `(deleted chat)` appended.
- Display the ledger timestamp (`WalletTransaction.created_at`) as the charge time. Use the linked exchange for model display name and tier, input/output tokens, and mode. Display credits charged as `-WalletTransaction.amount`, keeping the ledger as the accounting authority; `ChatExchange.credits_charged` should match that magnitude.
- Apply optional model and inclusive start/end date filters to the ledger queryset before computing results or totals. Date filtering should use the ledger timestamp, and reject an end date earlier than the start date. Populate model choices from models represented in the user's usage history, including inactive catalog models that still have historical charges.
- Show two totals across all pages: lifetime credits spent from the user's complete usage ledger, and credits spent by rows matching the active filters. Compute both from the ledger before pagination, with `-Sum(amount)` and empty results treated as zero. With no filters the values are equal; deleted chats are included in both applicable sums. Never total only the visible page or include top-ups/bonuses.
- Validate the GET filter form. If dates are malformed, the range is reversed, or a model is unknown/not among the user's historical models, show the validation error inline and render the unfiltered history rather than raising an error or applying a partial filter set.
- Order by `-created_at, -pk` and paginate the filtered rows at 20. Preserve active filter values in pagination links.
- Use `select_related('exchange__conversation', 'exchange__model')` for displayed rows so rendering chat title, model, and tier causes no per-row queries. Use a database aggregate for the total rather than loading all ledger rows into Python. Model filter options can be obtained with one distinct query over the user's usage rows.

## Privacy and URL Behavior

- Require authentication and scope the queryset to the requesting user's wallet, linked exchange owner, and conversation owner. The aggregate, model choices, rows, pagination count, and empty state must all derive from this scoped queryset so another user's usage cannot affect either visible data or totals.
- Filters are read-only GET parameters. Give the filter form an explicit Django `{% url %}` action; use named `{% url %}` reversals for the wallet link and page navigation. Preserve model/date parameters on pagination so generated URLs remain correct under `FORCE_SCRIPT_NAME`.
- Show only the requested accounting metadata, not prompt/reply contents.

## Verification

- Add offline MOCK tests that create successful exchanges and linked usage ledger entries without provider calls.
- Reconciliation coverage should compare the lifetime total to the negative sum of every user's ledger `usage` amount and the filtered total to the sum of matching ledger rows; verify each displayed charge matches its transaction and include a soft-deleted conversation. Also verify totals cover all matching rows, not only the current page.
- Privacy coverage should create charges for two users and prove the signed-in user's rows, model choices, and total include only their own entries.
- Cover both filters and inclusive date boundaries, invalid dates/ranges/models without a server error, 20-row pagination/newest-first ordering with filters preserved, deleted-chat labeling, empty state, and hosted-prefix link/form actions. A bounded-query assertion should catch per-row relationship queries.
- Cover both `mock` and `real` mode labels with stored exchange fixtures; mode-display tests need no real provider request. Keep all tests network-blocked and runnable in MOCK mode.

## Tradeoffs and Decisions

- A specialized page provides usage-specific columns and filters while the existing wallet page remains a complete mixed transaction ledger. Both use the same `WalletTransaction` rows, avoiding duplicate records and keeping totals reconcilable.
- The page reports both lifetime spend and the filtered subtotal. The filter subtotal is across every matching page, not a per-row cumulative balance, so both numbers can be reconciled to the corresponding ledger set.
- Filter dates are charge dates from the ledger, not exchange creation dates; those timestamps are usually close but the ledger timestamp is authoritative for reconciliation.
- Existing code hygiene caveat: `core/forms.py` defines `ConversationTitleForm` twice, and `core/tests.py` defines `ConversationSessionTests` twice. Python keeps the later module binding, so all seven test methods in the first class declaration are shadowed and not collected. In a separate refactor/test commit on the feature branch, give the two test classes distinct names, rename overlapping test methods so both versions run, and remove only the dead duplicate form declaration; retain both sets of tests and fix failures exposed by collecting them.
- The verified implementation policy for invalid filters is to show inline validation errors and leave the history unfiltered. No query, total, or pagination path should raise on user-supplied filter input.

## Out of Scope

No charts, streaming, file uploads, web search, new usage-history storage, or changes to charging/ledger creation are proposed.
