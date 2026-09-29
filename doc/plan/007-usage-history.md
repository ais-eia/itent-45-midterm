# Usage History Plan

- [x] Update `doc/study/007-usage-history.md` with the approved two-total accounting, invalid-filter behavior, and duplicate-test decisions.
- [x] Create a new feature branch for usage history.
- [x] In a separate Conventional Commit with `refactor:` or `test:`, fix the duplicate session declarations before adding feature tests: preserve both `ConversationSessionTests` versions under distinct class names, rename their overlapping test methods so all versions are collected, remove only the dead duplicate `ConversationTitleForm`, and correct duplicate setup/decorator scaffolding without removing assertions. Record that 7 test methods were previously shadowed, and run the suite to expose/fix any failures.
- [x] Add a `UsageHistoryFilterForm` with optional model, start date, and end date fields. Populate model choices only from the signed-in user's historical usage, including inactive models. Validate inclusive date ranges and start-before-end.
- [x] Make malformed dates, reversed date ranges, unknown model IDs, and models not present in the user's usage history safe: show inline form errors and render the unfiltered history rather than throwing a server error or applying a partially valid filter set.
- [x] Add an authenticated, read-only named usage-history route (proposed `/wallet/usage/`) and a link to it from the wallet page. Do not add a history table or migration; source each row from the existing `WalletTransaction` usage ledger.
- [x] Scope the base queryset to the request user's wallet, usage transaction type, linked exchange owner, and linked conversation owner. Keep soft-deleted conversations in the result set and append `(deleted chat)` to their titles.
- [x] Load row relations with `select_related('exchange__conversation', 'exchange__model')`. Display ledger charge timestamp, chat title/deleted label, model name and tier, input/output token counts, positive credits charged as `-amount`, and mock/real mode without exposing prompt/reply data or making per-row queries.
- [x] Compute lifetime credits spent from the unfiltered, owner-scoped usage ledger and filtered credits spent from the same queryset after valid model/date filters. Both totals must aggregate `-Sum(amount)` across all matching rows before pagination; empty totals are zero and deleted chats remain included.
- [x] Order filtered rows newest-first by ledger timestamp with a stable primary-key tie-breaker and paginate at 20 per page. Preserve current valid filters in pagination URLs.
- [x] Use Django `{% url %}` tags for the usage link, filter form action, and pagination links. Add `FORCE_SCRIPT_NAME` coverage for the filter action and links, including retained filter parameters.
- [x] Add MOCK-only offline tests for usage row metadata/mode, filtered and lifetime reconciliation to matching ledger `usage` sums, row-charge versus `ChatExchange.credits_charged`, a deleted chat included and labeled, model/date filters and inclusive boundaries, malformed/unknown filters, 20-row newest-first pagination, and filtered totals spanning pages.
- [x] Add a cross-user privacy test proving rows, filter model choices, filtered total, and lifetime total include only the signed-in user's usage transactions. Add a bounded-query test to detect per-row database queries.
- [x] Update README and `doc/wiki/` to describe usage-history columns, both totals, filters, deleted-chat inclusion, invalid-filter behavior, and the ledger as the source of truth.
- [x] Run Django checks, migration checks, the full test suite, and fresh-clone setup from README in MOCK mode; verify usage totals against wallet ledger rows and confirm the page works without a script prefix.
- [x] Review, commit feature work with Conventional Commits, clone/verify before merge, merge to `main`, verify the app after merge, and push to `origin main`.

## Decisions Captured

- Display two totals: lifetime usage spend and the total for the active filters. Both are ledger aggregates across all pages and include usage transactions for deleted chats.
- Invalid dates, reversed ranges, unknown models, and unowned models produce inline errors and an unfiltered history; invalid input must never crash the page.
- The duplicate `ConversationSessionTests` class shadowed 7 test methods. Preserve both sets, rename one class and the overlapping test methods so all tests run, remove only the duplicate form, and commit this cleanup separately as `refactor:` or `test:` on the feature branch.
