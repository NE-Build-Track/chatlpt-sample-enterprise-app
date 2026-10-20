# Design

ChatLPT should be recognizable to anyone who has used ChatGPT.

- **Layout:** a collapsible left sidebar (new chat, conversation list grouped by day, user menu at
  the bottom); a centered column of messages with a max width of about 48rem; a floating composer at
  the bottom with a stop button while streaming.
- **Messages:** user turns in a subtle bubble aligned right; assistant turns plain, full width,
  Markdown with syntax-highlighted code blocks and a copy button. A collapsible **Thinking** block
  above an assistant turn when reasoning was returned.
- **Costs:** a quiet one-line footer under each assistant turn: `1,204 in · 318 out · retail $0.0009
  · network $0.00003`. Network cost shows `pending` with a soft pulse until it arrives, and `unknown` (never $0) if the engine has no record. Hover explains
  both numbers and names the orchestrator.
- **Theme:** shadcn `neutral` palette, light and dark following the system, 14px base, Inter or the
  system stack. No gradients, no marketing.
- **Empty state:** the model name, where it runs (Livepeer), and three example prompts.
- **Admin:** a plain table page under the user menu for admins only.
- **Accessibility:** keyboard-first composer (Enter sends, Shift+Enter newline), focus rings,
  `aria-live` for streaming text, reduced-motion respected.
