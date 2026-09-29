# Model Catalog and Picker Study

## Request

Add a database-backed model catalog limited to OpenAI, Anthropic, and Google. Each row needs a display name, provider-specific `model_id`, exactly one tier (`value`, `standard`, or `premium`), input/output credit prices per 1,000 tokens, and an active flag. Seed the supplied provisional nine-model set so a fresh clone receives it after `migrate`. Add a page that presents active models grouped by provider or tier with prices, plus a way to activate/deactivate models. Do not make chat or provider calls.

## Feasibility

The project already uses Django models and data migrations in `core`, with SQLite and Django templates. The existing wallet can remain independent: catalog prices can be displayed without charging users. A model schema migration plus one catalog-seed data migration will make the catalog available on every fresh database without a committed `db.sqlite3` or new dependencies.

## Proposed Catalog Data

The following prices are invented provisional credits per 1,000 tokens, shared by tier across providers. They are not real-world prices. The `model_id` values are editable, unverified placeholders derived from the supplied display names; no API compatibility is claimed because this feature makes no provider calls.

| Provider | Display name | Provisional `model_id` | Tier | Input credits / 1k | Output credits / 1k |
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

## Proposed Approach

- Add a `CatalogModel` database model with provider choices restricted to OpenAI, Anthropic, and Google; separate `display_name` and `model_id` strings; a tier choice restricted to the three requested values; positive integer input/output credit rates; and `is_active` defaulting to true. Enforce `(provider, model_id)` uniqueness and valid tier/provider/price values at the database boundary where practical.
- Keep all nine runtime seed records and the provisional tier-price ladder together in one data migration. Make that migration depend on the catalog schema, use an idempotent update-or-create strategy keyed by provider and `model_id`, and ensure a fresh `migrate` produces the complete catalog. Do not split rows among fixtures, settings, and application code.
- Record the same provisional names, IDs, tiers, prices, and status in `doc/wiki/model-catalog.md`, visibly label the catalog provisional, and treat the wiki as the documented source of truth. Replacing provisional values before release should require editing one seed list and the wiki; after a migration has shipped, preserve migration history and use a follow-up data migration for changes to existing databases.
- Add a model catalog/picker page using Django templates. Show active models grouped by provider, with tier and both prices visible. The page may allow a user to select an active model in the UI, but that selection has no chat/API consumer yet and must not trigger wallet deductions.
- Provide activate/deactivate controls through Django admin for staff, rather than allowing ordinary users to change catalog availability. Regular users see only active models; staff can inspect inactive entries and toggle `is_active`.
- Test the seeded rows and prices, exact provider/tier restrictions, model ID uniqueness per provider, active filtering and staff toggling, page grouping/price display, and that rendering or selecting a model makes no provider request or wallet transaction. Update README and the project wiki.

## Tradeoffs and Risks

- The catalog is explicitly provisional. Prices are simple tier-based placeholders (value 1/2, standard 3/6, premium 9/18) and must not be presented as official or derived from provider pricing. Using the same ladder for all providers keeps the data easy to replace.
- Separate provider IDs from display names so official identifiers can be corrected without changing user-facing copy. The suggested IDs are placeholders only and must be reviewed before any real provider integration.
- One seed migration keeps the runtime catalog in one place, while the wiki documents it. Since applied migrations are immutable, corrections after release need a later migration even though the initial provisional list is centralized.
- An active flag is a catalog availability control, not model selection authorization or a provider capability check. No real API calls or claims that these provisional IDs work are part of this feature.
- The proposed model page selection is UI-only until a chat feature consumes a selected model. Persisting user preferences now would add state without a current consumer.

## Out of Scope

No chat completion calls, provider SDKs, API ID validation, real provider pricing, wallet charging, token accounting, or edits to provider credentials/configuration are proposed.
