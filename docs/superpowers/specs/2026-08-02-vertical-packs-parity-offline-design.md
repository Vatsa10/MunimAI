# Vertical Packs, Parity Pack, and Offline-First — Design

Date: 2026-08-02
Source strategy: `munim-vertical-strategy.md` (phases 1–3)

## 1. Scope

Three sub-projects, built concurrently by separate agents over a shared
foundation that this document fixes in advance.

| ID | Sub-project | Strategy phase |
|---|---|---|
| A | Vertical Pack infrastructure + hardware pack | 1 |
| B | Parity pack (all of §4.2 except batch/expiry) | 2 |
| C | Offline-first PWA | 3 |

**Explicitly out of scope:** batch/expiry tracking (the strategy doc gates it on
entering agri or pharma; the launch vertical is hardware), everything in §4.3
(double-entry accounting, payroll, e-invoicing IRP, BOM, generic CRM), phases 4–6
(barcode, mid-market, verticals 2–4).

**Not addressed by this design:** ambient-noise word error rate. The strategy
doc's Phase 0 gate — field ASR validation in five shops — requires voice minutes
that are not currently funded. It stays the largest unmeasured risk, and nothing
here reduces it.

## 2. Foundation contract (master-owned)

Lands as one commit before any sub-project agent starts. No agent may modify
anything in this section; they build against it.

### 2.1 Event type ordering

`ledger.py:_TYPE_ORDER` becomes:

```python
_TYPE_ORDER = {"opening_balance": 0, "stock_take": 0, "delivery": 1, "sale": 2,
               "sales_return": 3, "credit_note": 4, "debit_note": 4,
               "adjustment": 5}
```

A same-day return must replay after the sale it reverses, so `sales_return`
sorts below `sale`. `adjustment` moves from 3 to 5 and stays last; only relative
order affects replay, so existing behaviour is unchanged.

### 2.2 Stock effect of new event types

`_stock_detail` gains exactly one branch, added by the foundation rather than by
B, because it is part of the replay contract:

```python
elif t == "sales_return":
    qty_base += q
```

`credit_note` and `debit_note` are money-only. They deliberately get no branch:
the replay loop has no `else`, so unknown and money-only types are stock-neutral
by construction.

### 2.3 Client-generated event IDs

`sqlrepo.py` currently assigns `evt_0001` by selecting the highest existing id
and incrementing. An offline client cannot know the next number, and the
read-then-write is racy under concurrent writes.

Verified against the codebase: `sqlrepo.py` **already** accepts a caller-supplied
`event_id` and only mints `evt_NNNN` when one is absent. Offline clients can
therefore supply a ULID with no change to the insert path.

The real gap is idempotency. The insert has no conflict handling, so a replayed
outbox raises a unique-constraint violation rather than being a safe no-op. The
foundation adds `ON CONFLICT (user_id, event_id) DO NOTHING`, which turns the
existing `UNIQUE (user_id, event_id)` constraint into the idempotency guarantee.
No new dedupe column is required.

### 2.4 Sync ordering column

`ALTER TABLE events ADD COLUMN IF NOT EXISTS seq BIGINT;`

Server-assigned, monotonic per tenant, authoritative ordering on receipt. Added
now, unused until C.

### 2.5 Vertical configuration

`vertical_id` and `vertical_pack_version` are keys inside the existing
`user_config.data` JSONB column. No migration required.

New global table, versioned, read-only to tenants:

```sql
CREATE TABLE IF NOT EXISTS vertical_priors (
    vertical_id  TEXT NOT NULL,
    pack_version TEXT NOT NULL,
    phrase       TEXT NOT NULL,
    sku_ref      TEXT NOT NULL,
    attributes   JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (vertical_id, pack_version, phrase)
);
```

Tenant corrections continue to write to `learning`, never here.

### 2.6 Schema change rule

All new DDL is *appended* to `init_schema()` as idempotent statements
(`CREATE TABLE IF NOT EXISTS`, `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`). No
agent reorders or edits existing statements. This keeps three agents' schema
edits to trivial textual merges.

### 2.7 Frontend section markers

`frontend/index.html` gains named comment fences so B and C insert only within
regions they own:

```
<!-- @section:onboarding -->   (A)
<!-- @section:documents -->    (B)
<!-- @section:accounting -->   (B)
<!-- @section:offline -->      (C)
```

### 2.8 Contract test

`backend/test_ledger_contract.py` asserts replay order for all eight event types
and that money-only types leave stock unchanged. If any agent mangles
`_TYPE_ORDER`, this fails loudly rather than silently shifting stock.

## 3. Sub-project A — Vertical Pack

### 3.1 Goal

An owner records a real sale by voice within three minutes of signup, with zero
catalogue setup.

### 3.2 Pack layout

```
verticals/hardware/
  meta.yaml              # vertical_id, pack_version, display name
  catalogue_seed.jsonl   # ~150 reviewed SKUs: brand, grade, size, unit, GST
  alias_priors.jsonl     # spoken form -> sku_ref
  units.yaml             # bag/tonne/bundle/rft conversion factors
  attributes.yaml        # grade, diameter, brand, finish, length
  gst_map.yaml           # HSN + rate defaults per category
  prompt_fragment.md     # appended to the base Samvaad prompt
  reports.yaml           # which dashboards matter for this vertical
```

150 SKUs, not the strategy doc's 800–1500. A seeded catalogue with wrong grades
produces confidently incorrect matches, which is worse than a missing SKU that
falls through to the existing add-item flow. The 150 cover the highest-frequency
hardware transactions; coverage grows from reviewed additions, not bulk
generation.

### 3.3 Loader

New `backend/verticals.py`:

- `load_pack(vertical_id, version) -> Pack` — reads and validates the directory,
  caching per process.
- `seed_tenant(user_id, vertical_id)` — copies `catalogue_seed.jsonl` into the
  tenant's `skus`, writes `alias_priors` into `vertical_priors`, and stamps
  `user_config.data.vertical_id` / `vertical_pack_version`.
- Validation rejects a pack with unknown units, missing GST rates, or alias
  collisions, so a malformed pack fails at load rather than mid-conversation.

### 3.4 Matcher change

`matcher.py` resolution order becomes:

```
shop_alias -> shop_learned_prior -> vertical_prior -> substring/SKU -> fuzzy
```

`vertical_prior` slots *beneath* everything shop-specific, so a shop's own
learned vocabulary always wins over a shipped prior. This preserves the
compounding-moat property: shipped priors reduce cold start without ever
overriding what a shop has taught the system.

### 3.5 Prompt composition

`samvaad_config.py` composes base prompt + `prompt_fragment.md`. The 27-tool
registry is unchanged — this is deliberate, because changing the tool surface
would invalidate the Samvaad console configuration.

### 3.6 Onboarding

The onboarding step gains a vertical selector (hardware only at launch, so a
single-option control that records the choice rather than a chooser with one
item pretending to be a menu). Selecting it triggers `seed_tenant`.

### 3.7 Success criterion

A fresh signup can complete a voice sale of a seeded SKU without adding a
product. Measured by a test that seeds a tenant and resolves twenty
representative spoken phrases.

## 4. Sub-project B — Parity pack

Four sub-specs under one agent, built in this order.

### B1 — Documents

Delivery challan, quotation, proforma invoice, purchase order. All four reuse
the existing `reportlab` pipeline in `pdfs.py` and the token-protected document
links in `documents.py`. New templates only; no new delivery mechanism.

### B2 — Accounting events and Tally export

- Credit note, debit note, sales return — created through new endpoints, stored
  as the event types fixed in §2.1. Returns restore stock via §2.2.
- Tally/Busy export as XML. XML rather than CSV because Tally's own import path
  is XML; a CSV export pushes the mapping problem onto the accountant, which
  defeats the point of shipping it for CA gatekeeping.
- Export covers sales, purchases, returns, credit and debit notes, and payments
  for a date range.

### B3 — Import and price lists

- Bulk catalogue import from Excel/CSV with a dry-run preview: parse, match
  against existing SKUs, show what would be created versus updated, then commit.
  A destructive bulk import without preview is how shops lose their item master.
- Multi-rate price lists (retail / contractor / dealer) as a per-SKU rate map,
  with the customer carrying a default tier.

### B4 — Roles and print

- Multi-user staff accounts with per-role permissions. Roles: owner (all),
  manager (no deletion, no settings), staff (sale entry and lookup only).
  Enforced server-side in the existing auth middleware, not in the UI.
- Thermal (58mm/80mm) and A4 print layouts.
- Desktop/Windows path is satisfied by the PWA from C being installable; no
  separate native build.

### B5 — HSN/SAC and e-way bill

Verified against the codebase: `pdfs.py` renders GSTIN on the letterhead and a
CGST/SGST split, but **HSN/SAC codes and the e-way bill threshold do not exist**.
Both are table stakes on a GST invoice and must be built.

- HSN/SAC stored per SKU. It goes in the existing `skus.attributes` JSONB rather
  than a new column, and A's `gst_map.yaml` supplies category defaults so a
  seeded hardware catalogue arrives with HSN already populated. This is the one
  deliberate coupling between A and B: B consumes the key, A supplies the values,
  and B must degrade to a blank HSN when no vertical pack is loaded.
- E-way bill required above ₹50,000 invoice value. Scope is limited to surfacing
  the requirement and capturing the bill number on the invoice — **not**
  integration with the government e-way bill portal, which falls under the §4.3
  concession on IRP integration.

## 5. Sub-project C — Offline-first PWA

### 5.1 Scope boundary

Offline covers: sale entry, bill print, stock lookup, customer dues. It does not
cover invoice digitisation, WhatsApp send, or dashboards — all three are
inherently online and must show an explicit offline state rather than fail
silently.

### 5.2 Client

PWA with a service worker and IndexedDB, inside the existing single-file
`frontend/index.html`, within `<!-- @section:offline -->`. Installable on
Android, which is the real device target, and it satisfies B4's desktop
requirement without a native build.

### 5.3 Sync

Outbox pattern. The client writes events locally with ULID `event_id`s (§2.3),
queues them, and posts on reconnect. The server assigns `seq` (§2.4) and returns
authoritative ordering. Idempotency comes from `UNIQUE (user_id, event_id)`, so
a partially-delivered outbox is safe to resend wholesale.

### 5.4 Derived state

Snapshot plus local delta replay. The server ships a compact stock/dues snapshot;
the client applies local unsynced events on top. The ledger replay logic is
**not** ported to JavaScript — two implementations of stock maths would diverge,
and the divergence would surface as wrong stock numbers rather than as a crash.

### 5.5 Conflict resolution

Events are additive, so genuine conflicts are rare and confined to:

- **Stock takes:** timestamp wins.
- **Product edits:** last write wins, with an audit row.

### 5.6 Voice degradation

Offline falls back to the typed quick-entry path. Billing never blocks on voice
availability. This requires an explicit offline UI state.

## 6. Agent topology and merge protocol

```
master (Opus 5)
├── agent-A (Sonnet 5) — vertical packs      → Haiku workers: pack authoring, SKU review prep
├── agent-B (Sonnet 5) — parity pack         → Haiku workers: B1..B4 sub-tasks
└── agent-C (Sonnet 5) — offline PWA         → Haiku workers: service worker, IndexedDB layer
```

- Each agent runs in an isolated git worktree.
- File ownership is disjoint except `db.py`, `index.html` and `ledger.py`, which
  are governed by §2.6 (append-only DDL), §2.7 (section markers) and §2.1–2.2
  (frozen by the foundation).
- Merge order is A → B → C. This is not arbitrary: B5 consumes the HSN defaults
  that A's `gst_map.yaml` supplies, so A must land first. Master resolves
  conflicts and runs the full suite after each merge.
- No agent pushes to `main`. Master merges.

## 7. Testing

- Foundation: replay-order contract test (§2.8).
- A: pack validation test, and a twenty-phrase resolution test against a seeded
  tenant.
- B: one test per document type asserting the PDF renders and totals match the
  ledger; a Tally XML export test validating against Tally's expected element
  structure; an import dry-run test asserting no writes occur before commit;
  a permissions test asserting server-side enforcement per role.
- C: an offline round-trip test — queue events offline, reconnect, assert the
  server state matches and that a duplicate resend is a no-op.

Existing suite must stay green after each merge. The suite is self-contained —
`test_store.py` uses a fake Postgres store and temp directories, and no test
requires a live `DATABASE_URL`. Agents must keep it that way: any new test that
reaches for a real database is a defect, because it makes the suite unrunnable
in a worktree and tempts agents toward the shared Neon instance.

Agents run in the repo's `venv`, not system Python. The suite imports
`rapidfuzz`, `reportlab`, `psycopg` and `sarvamai`; a bare interpreter fails at
collection and produces failures unrelated to the change under test.

## 8. Risks

1. **Unmeasured ASR error rate under shop noise.** Phase 0 was never run. Nothing
   here mitigates it.
2. **`index.html` growth.** B adds four document types plus roles UI; C adds a
   service worker, IndexedDB layer and offline state. A 4,600-line file will
   roughly double and is the primary merge hotspot. Accepted deliberately in
   exchange for avoiding a refactor before the build.
3. **Seeded catalogue accuracy.** 150 LLM-generated SKUs require human review
   before shipping; unreviewed rows produce confident mismatches.
4. **Voice budget.** Sarvam credits are nearly exhausted, so A's voice path is
   testable only through the typed flow until that is resolved.
