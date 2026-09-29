# Chat Cost Estimate Study

## Request

Show a logged-in user an approximate credit cost before sending a chat message. Update it when the selected active model or prompt changes, label it clearly as an estimate, and warn if it exceeds the user's current balance. The displayed estimate and the metering pre-check must use the same estimation function. Keep any JavaScript dependency-free, make requests prefix-safe, and keep tests offline in MOCK mode.

## Existing Behavior

- `core/metering.py` provides `estimate_tokens(text)` and `credits_for_usage(model, input_tokens, output_tokens)`.
- `core/chat_service.py:create_exchange()` currently estimates input tokens from the submitted prompt, includes `LLM_MAX_OUTPUT_TOKENS` as the conservative output allowance, and uses those values for its affordability pre-check before selecting/calling a backend.
- The provider receives only the current prompt today. Conversation history is stored, but it is not assembled into the backend request, so it should not be counted in this feature's estimate. If a later change sends history, the same assembled input must be used by both the estimator and provider call.
- `ChatForm` already limits model choices to active catalog models, and the chat page renders the model selector, prompt field, and authenticated user's wallet balance in its shared header.

## Proposed Approach

- Extract the conservative pre-check calculation into one shared helper, for example `estimate_request_cost(model, prompt, max_output_tokens)`. It should estimate input tokens with `estimate_tokens(prompt)` and calculate credits with `credits_for_usage()` using the configured output-token allowance. Make `create_exchange()` call this helper so behavior remains unchanged.
- Add an authenticated, read-only estimate endpoint that accepts the active model ID and current prompt, validates the model server-side, and calls the same helper used by the pre-check. Return JSON containing the estimated credits, input-token estimate, output-token allowance, current balance, and whether the estimate exceeds that balance. Do not call a provider, write an exchange, or change the ledger.
- Add a small dependency-free script to the chat page. On prompt input and model change, debounce a POST to the estimate endpoint and update an accessible estimate/status region. Display the value as an estimate that includes the maximum output allowance, and show a distinct insufficient-balance warning when applicable. Include loading/error handling and ignore stale responses when the user changes inputs quickly.
- Render the endpoint URL into a `data-*` attribute using `{% url %}` and send the CSRF token from the chat form with the request. Do not hardcode a path or origin; URL reversal must continue to honor `FORCE_SCRIPT_NAME`.
- Keep the final POST pre-check authoritative. The preview can become stale if another request changes the balance; it is informational and must not reserve credits. The actual charge may differ from the displayed pre-check estimate because successful provider responses can report actual usage and MOCK replies use estimated output text. Clearly distinguish the conservative pre-send estimate from the eventual recorded charge.
- Test the shared helper and endpoint against `create_exchange()` pre-check inputs for the same model, prompt, and output-token setting. Cover prompt/model changes, balance warnings, invalid/inactive models, anonymous access, no backend/provider calls, no wallet/exchange writes, and script-prefixed form/fetch URLs. Run all tests with network access blocked in MOCK mode.

## Tradeoffs and Risks

- A server-backed estimate endpoint avoids duplicating token and credit arithmetic in JavaScript, so the preview and pre-check cannot drift. It adds a lightweight request while the user types; debounce requests and avoid logging prompt contents.
- The current pre-check includes the configured maximum output tokens, so the displayed estimate is conservative and may exceed the eventual charge. Label this explicitly rather than presenting it as a guaranteed final cost.
- The balance shown by the endpoint can become stale immediately; final submission must keep the existing pre-check and atomic debit behavior.
- No conversation history is sent today. If history is added later, update a shared input-construction helper so both provider requests and estimates count the same text.

## Out of Scope

No provider calls from the estimate endpoint, credit reservation, streaming, uploads, web search, or changes to final token accounting are proposed.
