# Quality score

Graded per domain and layer. Updated when a plan completes. Grades: A (tested, documented, no known
debt), B (tested, minor debt), C (works, gaps), D (scaffold), – (not started).

| Area | Grade | Notes |
| --- | --- | --- |
| Docs and map | B | Link-checked by `scripts/check_docs.py`; generated docs drift-checked by `tests/store/test_durability.py` |
| Contracts and layers | B | Frozen pydantic contracts; layering and confinement enforced by `tests/structure/` |
| Identity | C | Email/password and provider linking tested; the OAuth adapters themselves are untested against real providers (plan-03) |
| Conversations and chat | B | Reply pipeline tested with the scripted backend; streamed live through the engine (evidence 2026-10-19) |
| Context window | B | Derived from the smallest advertised window; output reserve capped at half the window; dropped turns reported; token estimate approximate (T1) |
| Billing (two books) | B | Retail exact and property-tested; wholesale filled and settled live; replies only (T6) |
| Admin | C | Routes and permissions tested; no quotas (phase 2) |
| Store and migrations | B | Contract suite runs on SQLite and the in-memory fake; migration drift test |
| HTTP and SSE | B | Routes, CSRF, ownership and the SSE frame format tested |
| UI | C | Builds, typed, zod at the boundary; verified in a real browser by screenshot; no automated browser test yet |
| Deploy and images | B | The full stack ran end to end with paid replies (evidence 2026-10-19); first-run script not yet exercised (T5) |
| Streaming (builder-core) | B | Implemented and shown live on the branch; awaiting Mike's and Josh's review |

## Test coverage

`uv run pytest --cov --cov-report=json && uv run python scripts/check_coverage.py`. The total floor is in
`pyproject.toml`; per-layer floors in `scripts/check_coverage.py` protect the layers that guard money and
correctness. Do not lower a floor to make a change pass.
