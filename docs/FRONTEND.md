# Frontend

Stack: **React 19, TypeScript (strict), Vite, Tailwind CSS v4, shadcn/ui**, `react-router`,
`zod` at the API boundary, `react-markdown` with `rehype-highlight` for replies. Package manager
**pnpm**, pinned by `packageManager` in `web/package.json`. Built to `web/dist` and served by
FastAPI as static files with SPA fallback.

## Conventions

- `web/src/api/`: one module per backend resource; every response parsed with a zod schema that
  mirrors the pydantic contract. No `any`.
- `web/src/components/ui/`: shadcn components as generated; do not hand-edit beyond theming.
- `web/src/features/<domain>/`: chat, conversations, auth, usage, admin. A feature owns its hooks,
  components and routes.
- Streaming: `EventSource`-style consumption through `fetch` + `ReadableStream`, so the request can
  carry the CSRF header and be aborted by the stop button.
- State: React Query for server state; no global store.
- Tests: Vitest for modules; `web/e2e/draw-smoke.mjs` drives the deployed app in headless Chromium with a saved
  session (`pnpm e2e:draw <base-url> <storage-state.json> "<prompt>"`), prints the page text, rendered images and
  console errors, and spends one image. Playwright is a dev dependency; `pnpm dlx playwright install chromium` once.

## Look and feel

See [DESIGN.md](DESIGN.md). In one sentence: it should feel like ChatGPT, with the two cost numbers
under each reply as the only unfamiliar thing.
