# Sub-project C — Offline-First PWA — Implementation Plan

Scope: spec section 5. Foundation (section 2) is already merged into this
worktree — `_TYPE_ORDER`/`_stock_detail`/`ON CONFLICT` idempotency/`events.seq`
all exist. This plan builds on top, touching only files this sub-project owns:
`backend/sync.py` (new), `backend/main.py` (new routes only), `backend/sqlrepo.py`
(new method, existing INSERT untouched), `backend/repo.py` (new method only),
`frontend/index.html` (only inside `<!-- @section:offline -->`), plus two new
static files `frontend/sw.js` and `frontend/manifest.webmanifest`.

## Global constraints
- Tests: `cd backend && DATABASE_URL= PYTHONIOENCODING=utf-8 <venv>/python.exe -m unittest discover -s . -p 'test_*.py'`. Baseline 223, must not regress.
- No test may touch a live database. Sync logic is tested against `JsonRepo`
  (file-backed, self-contained) and a `FakeRepo`, never `SqlRepo`/Postgres.
- Do not port ledger replay to JS. The client applies raw local events on top
  of a server-shipped snapshot using the SAME additive rules the spec already
  fixes (delivery +, sale -, sales_return +, adjustment ±, notes stock-neutral)
  but only for its own small unsynced set — never recomputing the full history.
- `backend/ledger.py` `_TYPE_ORDER`/`_sorted_events`/`_stock_detail`: read-only.
- `sqlrepo.py`'s `INSERT INTO events ... ON CONFLICT` statement: read-only.
  Seq assignment for Postgres happens via a separate `UPDATE`, added as a new
  method, so the insert text is untouched.

## Task 1 — `sync.py`: outbox apply (idempotent) + seq assignment
**Files:** create `backend/sync.py`, `backend/test_sync.py`.
- `apply_outbox(repo, events: list[dict]) -> dict` — for each event: if
  `event_id` already present among `repo.all_events()` (or already accepted
  earlier in this same call), record `{"event_id":, "status": "duplicate"}`
  and skip; otherwise assign the next per-tenant `seq` (max existing + 1),
  call `repo.append_event(event)`, and if the repo exposes
  `set_event_seq(event_id, seq)` (Postgres path) call it — JsonRepo just
  carries `seq` in the dict it already wrote.
  Returns `{"results": [...]}` — one entry per input event, in order.
- Resending the exact same list a second time must produce all `"duplicate"`
  and write nothing new — this is the round-trip contract test.
- Missing `event_id` -> `{"status": "rejected", "reason": "missing event_id"}`.

## Task 2 — `sync.py`: compact snapshot for delta replay
**Files:** extend `backend/sync.py`, `backend/test_sync.py`.
- `snapshot(repo) -> dict` — `{"as_of": today, "seq": <max seq seen>,
  "stock": {sku_id: {qty, unit, uncounted}}, "dues": {customer_id: {name,
  phone, outstanding}}}`. Reuses `ledger._stock_detail` and `crm.analytics`
  (or `crm.account`) — never reimplements replay.
- Client applies its own outbox events (already typed, already known) on top
  of this snapshot using the fixed additive rules for the four offline event
  types (`sale`, `delivery`, `sales_return`, `stock_take`/`opening_balance`,
  `adjustment`) — this bit of arithmetic is simple enough (net qty delta per
  sku) that duplicating it client-side does not risk diverging from
  `ledger.py`'s replay order, because the client never reorders anything; it
  only adds its own not-yet-synced events on top of an already-ordered
  snapshot.

## Task 3 — Sync HTTP routes
**Files:** extend `backend/main.py` (new section, does not touch existing
routes), `backend/test_agent.py`-style route test in `backend/test_sync.py`
using `TestClient` + a monkeypatched repo (matching the existing pattern in
`test_agent.py` — no live DB).
- `POST /api/sync/outbox` — body `{"events": [...]}` -> `sync.apply_outbox`.
- `GET /api/sync/snapshot` -> `sync.snapshot`.
- Both behind the existing session middleware (no changes needed there).

## Task 4 — Postgres seq assignment (production path, untested against a live DB)
**Files:** extend `backend/sqlrepo.py` with `set_event_seq(event_id, seq)` —
a plain `UPDATE events SET seq=%s WHERE user_id=%s AND event_id=%s`. Does not
touch the existing INSERT statement.

## Task 5 — Offline round-trip test (the required test)
**Files:** `backend/test_sync.py`.
- Build a temp-dir `JsonRepo`. Simulate "offline": build a small outbox of
  events with client-generated ULID-style `event_id`s (a sale, a delivery).
  Call `sync.apply_outbox` once ("reconnect") — assert server state (stock via
  `ledger.stock_at`) matches expectations and every result is `"accepted"`.
  Call `sync.apply_outbox` again with the SAME outbox ("resend") — assert
  every result is `"duplicate"`, `repo.all_events()` length unchanged, and
  stock is unchanged. This proves the idempotency guarantee end to end without
  a live database.

## Task 6 — PWA shell: manifest + service worker
**Files:** create `frontend/manifest.webmanifest`, `frontend/sw.js`. Register
from within `<!-- @section:offline -->` only.
- Manifest: name, short_name, start_url `/`, display `standalone`, icons
  (reuse an existing asset in `frontend/assets` if present, else a generated
  simple icon), theme/background color matching the existing page.
- Service worker: cache the app shell (`/`, this manifest, key assets) on
  install; network-first for `/api/*` GET reads with a cache fallback (stock
  lookup, dues) so those two offline-covered reads work when the network is
  down; POSTs to `/api/commit` / `/api/sync/*` are never intercepted by the
  service worker — they go through the IndexedDB outbox instead (see Task 7),
  because the service worker cannot itself replay ledger logic.
- Route `GET /manifest.webmanifest` and `GET /sw.js` need to be servable —
  check whether `main.py` already serves arbitrary files under `frontend/`;
  if not, add two trivial static routes (own-scope files only, no new
  middleware).

## Task 7 — IndexedDB outbox + offline UI state (frontend, `@section:offline` only)
**Files:** `frontend/index.html`, inside the fenced region only.
- A small vanilla-JS module (inline `<script>`, no bundler, no build step):
  - `openOutboxDB()` — one IndexedDB database, one `outbox` object store
    keyed by `event_id`.
  - `queueEvent(event)` — client generates a ULID `event_id` (a tiny inline
    ULID generator — no new dependency), stores the event locally, and
    updates the in-memory stock/dues view by applying the same additive
    delta rules as Task 2 (JS mirrors only the four-line delta, not the
    ledger's ordering/confidence/cost logic).
  - `flushOutbox()` — on `online` event or manual retry, POSTs everything
    still queued to `/api/sync/outbox`, then removes only the entries the
    server marked `accepted` or `duplicate` from IndexedDB (both mean "the
    server has it").
  - An offline banner bound to `navigator.onLine` / `online`/`offline`
    events, shown on the tabs this sub-project owns (sale entry, bill print,
    stock lookup, customer dues) plus an explicit "not available offline"
    state on invoice digitisation, WhatsApp send, and dashboards — those
    three must show the state, not silently fail.
  - Quick-entry fallback: when voice is unavailable (offline, or Samvaad
    session fails), a minimal typed form (product, qty, unit, rate, cash/
    credit) that calls the same `queueEvent` path — billing never blocks on
    voice.
- This is the one place the single-file-no-build-step constraint forces a
  real compromise: no TypeScript, no npm IndexedDB wrapper (idb), no proper
  ULID library — everything is hand-rolled inline JS. Documented as a known
  compromise in the final report, not hidden.

## Task 8 — Full suite + commit
Run the full suite, confirm 223 + new tests pass, commit each task
separately per TDD, no Claude attribution in commit messages.
