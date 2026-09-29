# Model Catalog

> **PROVISIONAL:** This catalog is a user-provided starting set. Provider model IDs are unverified placeholders and all credit prices below are invented for development. No model calls are made from the picker.

Prices are credits per 1,000 tokens. The same simple ladder applies across providers: value costs 1 input / 2 output credits, standard costs 3 / 6, and premium costs 9 / 18.

| Provider | Display name | Provisional `model_id` | Tier | Input credits / 1k | Output credits / 1k | Active by default |
|---|---|---|---|---:|---:|---|
| OpenAI | GPT-5.6 Luna | `gpt-5.6-luna` | value | 1 | 2 | Yes |
| OpenAI | GPT-5.6 Terra | `gpt-5.6-terra` | standard | 3 | 6 | Yes |
| OpenAI | GPT-5.6 Sol | `gpt-5.6-sol` | premium | 9 | 18 | Yes |
| Anthropic | Claude Haiku 4.5 | `claude-haiku-4.5` | value | 1 | 2 | Yes |
| Anthropic | Claude Sonnet 5.5 | `claude-sonnet-5.5` | standard | 3 | 6 | Yes |
| Anthropic | Claude Opus 5.5 | `claude-opus-5.5` | premium | 9 | 18 | Yes |
| Google | Gemini 3.1 Flash-Lite | `gemini-3.1-flash-lite` | value | 1 | 2 | Yes |
| Google | Gemini 3.8 Flash | `gemini-3.8-flash` | standard | 3 | 6 | Yes |
| Google | Gemini 3.1 Pro | `gemini-3.1-pro` | premium | 9 | 18 | Yes |

Staff can activate or deactivate entries in Django admin using the editable **Active** column. The user-facing picker lists active entries only. Update this wiki and the single catalog data seed together when the official catalog is available; after a migration ships, use a follow-up migration rather than rewriting applied migration history.
