# Session Management Study

## Request

Let each user keep multiple conversations, with a newest-first sidebar paginated 20 at a time. Support starting a new conversation, reopening and continuing an old one, renaming it, and deleting it. A conversation owned by another user must return 404. Preserve usage transactions and wallet audit history when a conversation is deleted. Keep model selection per exchange so a user can change models mid-conversation.

## Feasibility and Existing Storage

Feature 4 added `ChatExchange`, which stores one user/model/prompt/reply/token-count/credit-cost/timestamp record per successful request. There is currently no conversation/session model or grouping foreign key; the chat page lists a user's exchanges independently. `WalletTransaction.exchange` is a protected one-to-one relation, and usage entries are constrained to link to an exchange. Therefore session management should add a conversation parent to the existing exchanges, not a second message store. The existing login, mock backend, wallet debit service, and Django templates are sufficient; no new dependencies or provider calls are needed.

## Proposed Approach

- Add a `Conversation` model owned by the built-in user with a title, creation/activity timestamps, and a nullable deletion timestamp. Add a conversation foreign key to `ChatExchange`; keep the existing exchange/message fields and per-exchange `CatalogModel` relation so billing history and model changes remain intact.
- Existing exchanges have no grouping information. Use a reversible data migration to backfill each existing exchange into its own legacy conversation, using a truncated title derived from that exchange's prompt. This preserves the current independent-exchange semantics instead of guessing that unrelated old messages belong together. New conversations can contain multiple exchanges.
- Make `/chat/` a new-chat workspace and sidebar. A new-chat action starts a blank workspace without creating a database row on GET; create the conversation only when its first exchange is successfully persisted. Provide `/chat/<id>/` to reopen and continue a conversation.
- Store the first successful prompt as a whitespace-normalized, truncated title (suggested maximum 80 characters, with an ellipsis when truncated). Only set the title automatically while it is blank; later messages must not overwrite a manual rename. Add a rename form with a validated non-empty title and a POST-only CSRF-protected action.
- Add `last_activity_at` to conversations and update it when an exchange is appended, not when a title is renamed. Order the sidebar by `-last_activity_at` and a stable primary-key tie-breaker. Paginate the owner-filtered list with Django's `Paginator`, 20 conversations per page.
- Implement deletion as a soft delete by setting `deleted_at`. Exclude deleted conversations from the sidebar and make their detail/rename/delete routes return 404. Require a confirmation page before the state-changing POST delete. Keep their `ChatExchange` rows and linked usage `WalletTransaction` records untouched so the credit ledger remains auditable. The existing wallet transaction history must continue to list usage charges and mark entries from a deleted chat as `(deleted chat)`; future usage-history views should preserve the same label. This retains prompt/reply content in the database after it disappears from the user's UI; document that retention tradeoff.
- Scope every detail, rename, delete, and message query by both conversation ID and `request.user`; return 404 for a foreign-owned or deleted conversation rather than revealing that it exists. Use POST plus CSRF for rename and confirmed delete, and use `{% url %}` tags for all links/form actions so the hosted script prefix remains effective.
- Keep model choice on each submitted exchange. A conversation may default to the latest active model, but every message POST must revalidate its selected model as active. Existing exchanges retain their original model and cost; subsequent messages can use another active model.
- Update the chat service to attach every new `ChatExchange` to its conversation while preserving the existing no-reservation metering rules. Create a new conversation, its initial exchange, and the linked usage debit atomically after a successful backend reply. Provider errors or a failed final debit must not leave an empty conversation or exchange.
- Test mock-mode conversation creation/title truncation, multi-exchange continuation, per-exchange model and cost retention, newest-first pagination at the 20-item boundary, rename, delete confirmation/soft delete, deleted-chat ledger labeling, CSRF/method restrictions, and 404 behavior for cross-user detail/rename/delete/message requests. Include prefix-aware link/action checks, and keep tests offline in MOCK mode.
- Update README and `doc/wiki/` with conversation behavior, pagination, title generation, deletion/ledger retention, model switching, and hosted-prefix-safe URLs.

## Tradeoffs and Risks

- Soft deletion is the simplest way to make a chat disappear while preserving the protected exchange-to-ledger relationship and displaying its historical charge as `(deleted chat)`. It leaves prompt/reply text stored for audit and migration safety; permanent content erasure would need a separate approved retention/anonymization design that preserves charge records.
- Backfilling one conversation per existing exchange preserves current semantics but means older exchanges do not become one multi-message history. There is no stored information from which to reconstruct earlier grouping.
- Keeping `ChatExchange.user` while adding `ChatExchange.conversation` duplicates ownership data. Creation code and tests must ensure the exchange owner always matches the conversation owner; all reads must still filter by owner rather than trusting a client-supplied ID.
- Ordering by last activity makes a continued conversation move to the top; renaming or deleting it does not change its activity order.
- Deletion hides the conversation and all its exchanges from the owner-facing UI, but the usage transaction remains linked to the exchange and the soft-deleted conversation remains in storage.

## Out of Scope

No streaming, uploads, web search, provider behavior changes, conversation sharing, state-changing rename/delete via GET, hard deletion of usage records, or wallet refunds are proposed.
