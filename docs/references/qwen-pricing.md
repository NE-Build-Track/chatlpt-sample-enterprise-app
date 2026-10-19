# Qwen3.8-27B list prices (retail book)

**Status: to be filled in plan-04** from Alibaba Cloud Model Studio's international (Singapore)
price list, in USD per million tokens (D4). The machine-readable table is `config/pricing/qwen3.8-27b.json`
and the app loads it at startup; this page explains it.

| Field | Meaning |
| --- | --- |
| `input_per_m` | Prompt tokens not served from cache |
| `cached_input_per_m` | Prompt tokens served from the vendor's context cache (if listed) |
| `output_per_m` | Completion tokens in non-thinking mode |
| `thinking_output_per_m` | Completion tokens (including reasoning) in thinking mode (if listed separately) |
| `source_url`, `observed_at`, `region`, `currency` | Provenance |

Rules: retail = prompt × input + completion × output (or thinking output when reasoning was
returned). Tiered prices by input length, if the vendor lists them, are applied per request on the
prompt token count. Prices are never computed from wholesale.
