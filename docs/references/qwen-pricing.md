# Qwen3.8-27B list prices (retail book)

Observed on **2026-10-19** at
<https://www.alibabacloud.com/help/en/model-studio/qwen3-8-27b> (model id `qwen3.8-27b`), the
Singapore (International) region, in USD (D4). The machine-readable copy the app loads is
[`config/pricing/qwen3.8-27b.json`](../../config/pricing/qwen3.8-27b.json). Re-check the page before
quoting; Alibaba notes these are original rates excluding promotions.

| Billing item | USD per 1M tokens | Used as |
| --- | --- | --- |
| Input | 0.50 | `input_per_m` |
| Output | 3.00 | `output_per_m` |
| Input, implicit cache hit | 0.10 | `cached_input_per_m` |
| Explicit cache creation | 0.625 | not used (we never create explicit caches) |
| Explicit cache read | 0.05 | not used |

Thinking and non-thinking modes share one price list, so `thinking_output_per_m` is `null` and
reasoning tokens are priced as output. For reference, the Beijing region lists 0.424 input and
1.696 output; it is not used.

Model limits the vendor states: context window 1,000,000 tokens; max input 991,808 (983,616 in
thinking mode); max output 131,072; max chain of thought 262,144. **These are the vendor's limits,
not the Livepeer runner's.** The runner's own `max_model_len` governs the context window (D14).

## Rule

`retail = (uncached_prompt × 0.50 + cached_prompt × 0.10 + completion × 3.00) / 1,000,000`, where
`cached_prompt` is `usage.prompt_tokens_details.cached_tokens` when the runner reports it, otherwise 0.
Retail is never computed from wholesale, and wholesale is never computed from retail.
