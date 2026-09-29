# Metered Chat Plan

- [x] Record the approved decisions in `doc/study/005-metered-chat.md` and note the no-reservation limitation in `doc/wiki/credit-wallet.md`.
- [x] Create a new feature branch for metered chat.
- [x] Add environment-backed proxy configuration: shared `LLM_PROXY_BASE_URL`, optional `OPENAI_PROXY_BASE_URL` / `ANTHROPIC_PROXY_BASE_URL` / `GOOGLE_PROXY_BASE_URL` overrides, `LLM_PROXY_REQUEST_STYLE` (`openai_compatible` or `provider_native`), and `LLM_MAX_OUTPUT_TOKENS` with a default of 512. Resolve a provider override before the shared endpoint. Use MOCK only if no applicable proxy URL is configured; a configured URL without its provider key/style is a sanitized error, not MOCK.
- [x] Change `.env.example` so the shared/per-provider proxy URLs, request style, and provider-key values are blank/commented. Do not include any URL literal or credential value; ensure fresh setup selects MOCK.
- [x] Add a provider-neutral request/result interface and deterministic no-network `MockBackend`; add `ProxyBackend` provider/style adapters for OpenAI, Anthropic, and Google. Send the catalog's provisional `model_id`, select the correct provider key from the environment, use only configured endpoints, and never log/print keys or raw request headers.
- [x] Make configured REAL transport/provider failures return a sanitized error, create no exchange, and cause no debit. Do not silently fall back to MOCK. Normalize provider token usage when available and estimate missing input/output counts from text length; record which counts were estimated.
- [x] Add a `ChatExchange` model and migration for user, catalog model, prompt, reply, token counts, credits charged, MOCK/REAL mode, estimation metadata, and timestamp. Add an optional exchange FK to `WalletTransaction` and a database constraint that usage entries require an exchange while signup/top-up entries remain unlinked.
- [x] Add token-estimation and integer credit-cost helpers that use the catalog's input/output rates and round combined cost up once per exchange.
- [x] Add a conservative pre-check using estimated prompt tokens plus `LLM_MAX_OUTPUT_TOKENS` at the active model's rates. If balance is too low, show an insufficient-credit message and do not call the backend. Do not add a reservation or hold.
- [x] Add a login-required chat view/page with active catalog-model selection and prompt submission. Revalidate the selected model as active on the server; store each prompt/reply as an independent exchange and display its model, MOCK/REAL label, and credit cost. Keep chat session grouping and sidebar behavior out of scope.
- [x] Calculate charge as the ceiling of combined input/output token costs over 1,000 tokens using integer arithmetic. Meter successful MOCK replies using estimated token counts and the same charge path as REAL replies.
- [x] After a successful backend reply, atomically create the exchange and call the existing wallet service for a negative `usage` transaction linked to it. If the final debit fails because the balance changed after pre-check, roll back the exchange, discard the reply, charge nothing, and show a clear retry message. Preserve the limitation that the provider may still have incurred cost for the discarded reply.
- [x] Add fully offline tests with proxy configuration absent and outbound HTTP blocked. Cover mock labels/estimated counts/charges, model active filtering, insufficient pre-check without backend call, configured proxy failure without MOCK fallback or charge, provider token usage and missing-usage estimation, integer rounding, exchange/ledger linkage, provider failure with no persisted data, final-debit failure rollback/discard, and non-negative wallet balance.
- [x] Add a key-redaction test that injects only a generated synthetic non-secret sentinel into a mocked provider exception and asserts that it is absent from captured logs and rendered errors. Never use a real key in the test suite.
- [x] Update README and `doc/wiki/` with chat use, mock-default behavior, REAL proxy configuration variable names, per-exchange metering, provisional model IDs, and the no-reservation concurrency/provider-cost limitation. Include no credentials or proxy URL values.
- [x] Run Django checks/tests and verify a fresh migration works in MOCK mode with network access blocked.
- [ ] Clone into `/tmp`, follow only README setup, confirm migrations/server startup, demo login, and a charged mock exchange with a linked usage ledger; remove the temporary clone.
- [ ] Review and commit with Conventional Commits, merge to `main`, verify the app after merge, and push to `origin main`.

## Approved Runtime Decisions

- No credit reservation: check estimated affordability before the request, then debit atomically after a successful reply. If the final debit fails, discard the exchange and reply without charge and ask the user to retry; a provider may have incurred cost.
- MOCK is selected only when no applicable proxy URL is configured. A configured proxy failure or missing provider credential is an error, never a fallback to MOCK.
- Successful MOCK replies are visibly labeled and charged using estimated token counts.
