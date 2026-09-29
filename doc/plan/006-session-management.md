# Session Management Plan

- [x] Update the approved study in `doc/study/006-session-management.md` with the decisions on per-exchange migration, soft delete, deleted-chat ledger labels, per-message models, and delete confirmation.
- [x] Create a new feature branch for session management.
- [x] Add a `Conversation` model with owner, title, creation time, `last_activity_at`, and `deleted_at`; index owner/activity for newest-first listing. Keep the existing `ChatExchange` rows and add a conversation relation rather than duplicating message data.
- [x] Add reversible migrations in stages: create conversations and a nullable exchange FK; data-migrate each existing exchange into its own legacy conversation with a truncated prompt title and preserved timestamps; make the FK non-null. The reverse data migration must detach exchanges before the schema is removed.
- [x] Implement title generation from the first successful prompt: normalize whitespace, truncate to the chosen title limit, and only set it when blank so later messages do not overwrite a user rename.
- [x] Change `/chat/` into a sidebar/new-chat workspace, create a conversation only when its first exchange succeeds, and add `/chat/<id>/` to reopen and continue it. Paginate the owner-filtered sidebar newest-first with exactly 20 conversations per page.
- [x] Keep model selection on every message POST. Revalidate that the selected catalog model is active; persist the selected model and its own metered cost on each `ChatExchange`, allowing model changes within a conversation.
- [x] Add owner-scoped conversation lookups for detail, continue, rename, delete confirmation, and delete; return 404 for foreign-owned or soft-deleted chats.
- [x] Add a rename form/endpoint that is POST-only, CSRF-protected, and validates a non-empty bounded title. Do not let rename change `last_activity_at`.
- [x] Add a GET delete-confirmation page with a CSRF-protected POST confirmation. Only POST soft-deletes by setting `deleted_at`; GET and failed/invalid confirmation must not mutate the conversation.
- [x] Preserve `ChatExchange` and `WalletTransaction` rows when a conversation is soft-deleted. Update the existing wallet transaction history to keep usage charges visible and append `(deleted chat)` for charges whose conversation is deleted.
- [x] Update chat service transactions so a new conversation, first exchange, and linked usage debit commit atomically after backend success; append exchanges and update `last_activity_at` for existing conversations. Provider failure or final debit failure must leave no new exchange or conversation.
- [x] Use `{% url %}` tags for sidebar links, pagination, new-chat, rename, confirmation, delete, and message forms. Add prefix-aware test-client coverage for all affected links/actions under `FORCE_SCRIPT_NAME`.
- [x] Add MOCK-only offline tests for reversible migration/backfill, new-chat title truncation, continuing multi-exchange histories, model switching/costs per exchange, 20-item pagination/order, rename, GET confirmation plus POST-only deletion, CSRF checks, deleted-chat ledger labeling/preservation, and cross-user 404s for detail/continue/rename/delete.
- [x] Update README, `doc/wiki/`, and the credit-wallet wiki so session behavior, title rules, pagination, model changes, delete confirmation, soft-delete retention, and deleted-chat history labeling are documented.
- [x] Run Django checks/tests and verify existing and fresh databases migrate correctly in MOCK mode.
- [x] Clone into `/tmp`, follow only README setup, verify demo login, two chats, model-switch continuation, rename, confirmed soft delete, balance and ledger retention, and stored exchanges; verify pagination and hosted-prefix URLs in tests, then remove the temporary clone.
- [x] Review and commit with Conventional Commits, merge to `main`, verify after merge, and push to `origin main`.

## Decisions Captured

- Existing independent exchanges each become one legacy conversation; new sessions can contain multiple exchanges.
- Deletion is a CSRF-protected confirmed POST soft delete. Exchanges and ledger entries remain; usage history labels retained charges from a deleted conversation as `(deleted chat)`.
- Every message retains its own model and price/cost; models can change mid-conversation.
