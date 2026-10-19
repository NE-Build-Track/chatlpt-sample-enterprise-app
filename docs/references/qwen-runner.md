# The `blueclaw/chat/qwen3.8-27b` runner

Observed through the engine on 2026-10-14, 2026-10-17 and 2026-10-19 (builder-core evidence and the
studio's `runner-schemas/blueclaw_chat_qwen3.8-27b.openapi.json`). Re-verify on first paid call.

- A **vLLM** OpenAI-compatible server. Paths: `/v1/chat/completions`, `/v1/completions`,
  `/v1/responses`, `/v1/messages`, `/v1/models`, `/tokenize`, `/detokenize`, `/health`.
- `GET /v1/models` lists one model, `Qwen3.8-27B`, with `max_model_len` (vLLM's model card). This is
  the context window (D14).
- `ChatCompletionRequest` supports `stream`, `stream_options` (`include_usage`), `include_reasoning`,
  `reasoning_effort`, `thinking_token_budget`, `max_tokens`, `temperature`, `top_p`, `tools`.
  The `model` field may be omitted; the runner serves one model.
- Non-streaming reply: standard chat completion body, `choices[0].message.content`,
  `choices[0].message.reasoning` (null or empty so far), `usage.{prompt,completion,total}_tokens`.
  Reasoning tokens, when present, are inside `completion_tokens`; vLLM may also report
  `usage.completion_tokens_details.reasoning_tokens`. Record both when present.
- Streaming reply (`stream: true`): `text/event-stream`, `data: {...}` chunks with
  `choices[0].delta.content` and `choices[0].delta.reasoning`, then a final chunk with `usage` when
  `stream_options.include_usage` is true, then `data: [DONE]`.
- **Billed per second** of the call ($0.0000111/s observed), not per token. Short replies took
  2.4–2.9 s end to end; cost about $0.00003 each.
- Observed on speedybird and xode. open-pool and hky were discovered but not routed to.
- **Discovery metadata (2026-10-19):** the runner's entry carries
  `{"blueclaw":1,"capability":"openai:chat-completions","unit":"tokens","model_id":"Qwen3.8-27B","name":"Qwen 3.8 27B","category":"chat","max_context":131072}`,
  which matches vLLM's `max_model_len` of 131072 on xode and hky; **speedybird advertises `max_context` 40960**
  for the same app. ChatLPT takes the smallest across the approved runners instead of paying for `GET /v1/models` (D14).
- **Continuation:** `continue_final_message: true` with `add_generation_prompt: false` makes vLLM continue the
  trailing assistant turn; ChatLPT uses it for "Continue generating" (D24). `reasoning_effort` and
  `thinking_token_budget` are accepted for the thinking level.
- **Reasoning:** with `chat_template_kwargs.enable_thinking: true` the reply carries `message.reasoning`, but
  `usage.completion_tokens_details` was absent, so reasoning tokens are counted inside `completion_tokens`.
- **Cost arrives in rounds.** A 5.7 s reply produced two usage rows ($0.000111 + $0.000056); the engine's cost
  for a job can therefore grow after its first observation, and its status is `none` for about 16 s after the
  job ends. See [evidence](evidence/2026-10-19-first-paid-replies.md).
