# Fraud War Room model routing

The deterministic workbench runs first for every tier. The router then chooses optional model-backed opinions:

| Tier | Work | Provider strategy |
| --- | --- | --- |
| LOW | Exact signals and safe monitor decision | At most one configured fast provider; local summary otherwise |
| MEDIUM | Evidence and graph verification | One configured worker provider with fallback |
| HIGH | Full investigation, attack/defense loop, simulation, challenger | Up to three independent configured providers; disagreement triggers evidence retrieval |
| CRITICAL | Full evidence package and mandatory human decision | Multiple independent opinions; no autonomous execution |

Supported configuration roles are NVIDIA, Cerebras, Gemini, and optional Sarvam. The router reads `NVIDIA_API_KEY`, `CEREBRAS_API_KEY`, `GEMINI_API_KEY`, and `SARVAM_API_KEY` plus `FRAUD_*_MODEL` and `FRAUD_*_BASE_URL`. Cerebras uses `qwen-3.8-27b` at `https://api.cerebras.ai/v1` by default after `CEREBRAS_API_KEY` is set; the model and endpoint remain overridable for a dedicated deployment. Other providers stay opt-in until their model and endpoint are configured.

The actual Neuro SAN network uses the established HOCON include convention with the isolated `config/fraud_defense_llm_config.hocon` file. The network topology does not contain provider secrets. Cerebras Qwen 3.8 27B is the primary native network model through the OpenAI-compatible adapter; Gemini and NVIDIA remain fallbacks. Change the native fallback order in that config without editing `registries/industry/fraud_defense.hocon`.

When no provider is configured, HIGH and CRITICAL cases use three explicitly labelled local heuristic opinions—behavioral, graph, and conservative risk—for deterministic offline disagreement testing. These are not represented as external model calls. Provider errors are recorded and fall back to the local opinions.

Sarvam voice/STT/TTS is an optional extension point. It is not on the core path and is intentionally not required for the fraud-defense loop.
