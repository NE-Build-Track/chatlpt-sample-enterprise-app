# Tech debt

| # | Shortcut | Why it is acceptable now | Pay it when |
| --- | --- | --- | --- |
| T1 | Token counting before a call is an estimate (previous `prompt_tokens` plus characters/4 for the new turn). | The runner's `usage` gives exact counts after the fact; the estimate only decides truncation. | A local Qwen tokenizer is vendored, or the runner's `/tokenize` is cheap enough to call. |
| T2 | Replies are buffered until the streaming branch lands (D2, D20). | The UI and services already handle streams. | plan-06. |
| T3 | Orchestrator TLS certificates are pinned trust-on-first-use (copied from builder-core's dev-stack). | The listed orchestrators serve self-signed certificates today. | They serve CA-signed certificates. |
| T4 | No CI (D13). | Checks are listed in AGENTS.md and run locally. | v2. |
