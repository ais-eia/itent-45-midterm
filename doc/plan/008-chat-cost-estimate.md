# Chat Cost Estimate Plan

- [x] Confirm the approved scope and existing pre-check behavior in `doc/study/008-chat-cost-estimate.md`.
- [x] Create a new feature branch for the chat cost estimate.
- [x] Verify duplicate session test/form cleanup is already present in the branch base (`eab6c16 refactor: restore shadowed session tests`): both session test classes are distinct and the duplicate form declaration is absent. Seven previously shadowed tests were restored; no redundant cleanup commit is needed in this feature branch.
- [x] Add a shared helper in `core/metering.py` that accepts an active catalog model, prompt text, and output-token allowance, and returns estimated input tokens, the output allowance, and the conservative credit estimate using the existing token and credit helpers.
- [x] Refactor `core/chat_service.py:create_exchange()` to use the shared helper for its affordability pre-check without changing the current limit, debit, or error behavior.
- [x] Add a login-required, read-only POST estimate endpoint that validates an active model and prompt, calls the shared helper, and returns estimated credits, token estimate, output allowance, current wallet balance, and an exceeds-balance flag as JSON. It must not call a backend/provider or write exchanges or ledger transactions.
- [x] Add a named URL for the estimate endpoint and ensure anonymous, malformed, unknown-model, and inactive-model requests receive safe, deterministic error responses.
- [x] Add a clearly labeled estimate/status region to `core/templates/core/chat.html`. Include the endpoint URL via a `{% url %}`-generated data attribute and expose the form's CSRF token to the client script.
- [x] Add small dependency-free JavaScript that requests estimates when prompt text or model selection changes, debounces input, handles loading/errors, and ignores stale responses. Show the conservative output allowance in the label and warn when estimated cost exceeds the current balance.
- [x] Keep the final chat POST pre-check authoritative; do not add credit reservations. Do not include conversation history in estimates while provider requests send only the current prompt.
- [x] Add offline tests proving the shared helper's estimate matches the chat pre-check for identical inputs; cover endpoint estimates/warnings, logged-out and invalid/inactive requests, no backend calls, and no exchange or wallet writes during estimation.
- [x] Add template and hosted-prefix tests for the estimate endpoint URL, form action, and CSRF wiring; verify client-side updates are triggered by prompt and model changes without introducing a frontend dependency/build step.
- [x] Update README and `doc/wiki/` to explain the conservative estimate, output-token allowance, balance warning, and the distinction between the pre-send estimate and final metered charge.
- [x] Run Django checks, migration checks, and the full test suite with network access blocked in MOCK mode.
- [ ] Clone into `/tmp`, follow only the README setup, confirm migrations/server startup and demo login, and verify the estimate updates for prompt/model changes without changing the wallet or creating an exchange; then remove the temporary clone.
- [ ] Review and commit with Conventional Commits, merge to `main`, verify after merge, and push to `origin main`.

## Decisions Captured

- The preview and metering pre-check call the same server-side estimation helper; JavaScript does not duplicate pricing/token arithmetic.
- The current provider request contains only the submitted prompt, so conversation history is not included in the estimate.
- The displayed estimate is conservative because it includes `LLM_MAX_OUTPUT_TOKENS`; actual successful charges can differ when provider usage or MOCK reply estimates are available.
- The preview is informational and may become stale; the existing final pre-check and atomic debit remain authoritative.
