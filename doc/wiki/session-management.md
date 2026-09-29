# Chat Sessions

- Each saved `Conversation` belongs to one user and groups existing `ChatExchange` messages; it does not duplicate prompt/reply data. A message retains its own active catalog model, token counts, mode, and charged credits, so the model can change between turns.
- `/chat/` starts a new-chat workspace. A conversation is created only after its first successful message, with a title generated from that prompt and truncated to 80 characters. Later messages do not replace the title; users may rename it.
- Existing independent exchanges are migrated one exchange per legacy conversation. The reversible data migration detaches exchanges on reverse, preserving their prompt/reply and wallet ledger data.
- The sidebar is owner-filtered, ordered by latest activity, and paginated 20 conversations at a time. Reopening a conversation loads its full message history; continuing it updates its activity time.
- Chat detail, message submission, rename, delete confirmation, and delete actions all verify conversation ownership. A different user's conversation returns 404. Rename is a CSRF-protected POST and does not change activity ordering.
- Delete requires a confirmation page and POST; it sets `deleted_at` rather than deleting the conversation or exchanges. Usage wallet transactions remain linked and auditable. The wallet transaction history labels a charge from a deleted conversation as `(deleted chat)`.
- Links and form actions use Django named URL reversals so `FORCE_SCRIPT_NAME` keeps them under a hosted path prefix.
- Streaming, uploads, web search, conversation sharing, and hard deletion are not implemented.
