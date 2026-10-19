# Tech debt

| # | Shortcut | Why it is acceptable now | Pay it when |
| --- | --- | --- | --- |
| T1 | Token counting before a call is an estimate (previous `prompt_tokens` plus characters/4 for the new turn). | The runner's `usage` gives exact counts after the fact; the estimate only decides truncation. | A local Qwen tokenizer is vendored, or the runner's `/tokenize` is cheap enough to call. |
| T2 | Replies are buffered until the streaming branch lands (D2, D20). | The UI and services already handle streams. | plan-06. |
| T3 | Orchestrator TLS certificates are pinned trust-on-first-use (copied from builder-core's dev-stack). | The listed orchestrators serve self-signed certificates today. | They serve CA-signed certificates. |
| T4 | No CI (D13). | Checks are listed in AGENTS.md and run locally. | v2. |
| T5 | `deploy/first-run.sh` has not been run end to end; the grant and key were created by hand on 2026-10-19 while learning the CLI's output. | The script encodes the same two commands and refuses to overwrite an existing key. | The next fresh stack (or a second grant) runs it and the evidence records it. |
| T6 | The wholesale book covers replies only. Engine jobs the app runs for itself (the `GET /v1/models` probe) are paid but not in the ledger. | The probe runs only when discovery metadata is missing, and the engine's own `costs.summary` has the full figure. | An admin view of the engine's cost summary and reconciliation (plan-04 or later). |
