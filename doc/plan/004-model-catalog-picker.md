# Model Catalog and Picker Plan

- [x] Confirm the approved scope and provisional data in `doc/study/004-model-catalog-picker.md`.
- [x] Create a new feature branch for the model catalog and picker.
- [x] Add a `CatalogModel` table with exact provider choices (OpenAI, Anthropic, Google), separate display name and provisional provider `model_id`, exact tier choices (`value`, `standard`, `premium`), positive integer input/output credits per 1,000 tokens, and `is_active` defaulting to true.
- [x] Add database constraints for allowed providers/tiers, positive prices, and unique `(provider, model_id)` pairs.
- [x] Add and commit the catalog schema migration.
- [x] Add one data migration containing all nine provisional seed rows in a single list: the supplied provider/name/tier set, editable provisional model IDs, and the tier ladder value 1/2, standard 3/6, premium 9/18 input/output credits per 1,000 tokens. Make the seed idempotent and depend on the schema migration.
- [x] Register the catalog model in Django admin with provider/name/model ID/tier/prices visible and `is_active` in `list_editable`, so staff can activate or deactivate entries without a custom toggle page.
- [x] Add a user-facing `/models/` picker page showing active models grouped by provider with their display names, tiers, provider IDs, and both prices. Allow an in-page UI selection only; do not persist a preference or make chat/provider calls.
- [x] Ensure inactive models are hidden from the user-facing picker while remaining available to staff in Django admin.
- [x] Add tests for the nine seeded rows and provisional prices/IDs, seed availability after migrations, provider/tier/price constraints, per-provider ID uniqueness, active filtering, admin list editing, picker grouping/content, and no provider calls or wallet changes.
- [x] Update `doc/wiki/model-catalog.md` with the exact catalog and prices, prominently marked **PROVISIONAL**, and update README/wiki to explain the picker, admin activation, and unverified model IDs.
- [x] Run Django checks/tests and verify catalog migrations from an empty database.
- [x] Clone into `/tmp`, follow only the README setup, confirm migrations, catalog contents, server startup, and demo login; then remove the temporary clone.
- [x] Review and commit with Conventional Commits.
- [x] Merge to `main`, confirm the app works after merge, and push to `origin main`.

## Provisional Data To Seed

| Provider | Display name | `model_id` placeholder | Tier | Input / 1k | Output / 1k |
|---|---|---|---|---:|---:|
| OpenAI | GPT-5.6 Luna | `gpt-5.6-luna` | value | 1 | 2 |
| OpenAI | GPT-5.6 Terra | `gpt-5.6-terra` | standard | 3 | 6 |
| OpenAI | GPT-5.6 Sol | `gpt-5.6-sol` | premium | 9 | 18 |
| Anthropic | Claude Haiku 4.5 | `claude-haiku-4.5` | value | 1 | 2 |
| Anthropic | Claude Sonnet 5.5 | `claude-sonnet-5.5` | standard | 3 | 6 |
| Anthropic | Claude Opus 5.5 | `claude-opus-5.5` | premium | 9 | 18 |
| Google | Gemini 3.1 Flash-Lite | `gemini-3.1-flash-lite` | value | 1 | 2 |
| Google | Gemini 3.8 Flash | `gemini-3.8-flash` | standard | 3 | 6 |
| Google | Gemini 3.1 Pro | `gemini-3.1-pro` | premium | 9 | 18 |

The IDs and prices are placeholders, not verified provider identifiers or real-world pricing. The Django admin active flag is the sole availability toggle; Django admin pages are outside the user-facing picker header scope established in the wallet plan.
