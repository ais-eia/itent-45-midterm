# Usage History

- `/wallet/usage/` is an authenticated read-only view backed by the signed-in user's `WalletTransaction` rows with type `usage`. The wallet ledger remains the source of truth; this page does not persist a second history.
- Each usage transaction has a negative amount and one linked exchange. The page displays the ledger charge timestamp, chat title, model and tier, input/output token counts, positive credits charged (`-amount`), and mock/real mode. A soft-deleted chat's title is suffixed `(deleted chat)` and its charge remains included.
- Two totals are shown: lifetime credits spent from every usage transaction owned by the user, and the subtotal for the selected model/date filters. Both sum negative ledger amounts across all pages; they exclude signup bonuses and top-ups. With no filters they match.
- Model choices are limited to models in the user's own usage history, including inactive catalog entries needed for old charges. Date filters are inclusive charge dates from `WalletTransaction.created_at`; selected filters are combined.
- Invalid dates, reversed date ranges, unknown models, and models not in the user's history display inline form errors and render the unfiltered history rather than failing or partially filtering data.
- Queries are scoped to the user's wallet, exchange, and conversation. Related exchange/model/conversation rows use `select_related`, and totals use database aggregates before pagination. Results are newest-first, 20 per page; navigation preserves valid filters.
- Filter actions and links use named Django URL reversals so hosted `FORCE_SCRIPT_NAME` prefixes work.
- Tests create usage fixtures in offline MOCK mode, reconcile both totals to matching ledger transactions, cover deleted chats and cross-user privacy, filters, pagination, bounded query counts, and prefixed links.
