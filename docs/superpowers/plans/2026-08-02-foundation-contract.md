# Foundation Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the shared contract — event replay ordering, idempotent event insertion, schema-append rule, and frontend section markers — so sub-projects A, B and C can be built concurrently without silently corrupting each other.

**Architecture:** Additive changes only. The event enum gains three types whose replay ranks are chosen so existing relative ordering is unchanged; event insertion becomes idempotent via the constraint that already exists; new schema is appended as idempotent DDL. Nothing here changes current behaviour for any existing event.

**Tech Stack:** Python 3.12, FastAPI, psycopg 3, PostgreSQL (Neon), plain HTML/JS frontend.

## Global Constraints

- Run everything with the repo venv: `./venv/Scripts/python.exe`. A bare interpreter fails at import (`rapidfuzz`, `reportlab`, `psycopg`, `sarvamai`).
- All new DDL is appended to `init_schema()` and must be idempotent (`CREATE TABLE IF NOT EXISTS`, `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`). Never reorder or edit existing statements.
- No test may require a live `DATABASE_URL`. The suite is self-contained and must stay that way.
- Money-only event types must remain stock-neutral by construction — do not add `else` branches to the replay loop.
- Commit messages carry no Claude attribution.

---

### Task 1: Event type ordering and the sales_return stock branch

**Files:**
- Modify: `backend/ledger.py:21-22` (`_TYPE_ORDER`), `backend/ledger.py:88-90` (`_sorted_events`), `backend/ledger.py:113-124` (`_stock_detail` replay loop)
- Test: `backend/test_ledger_contract.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `ledger._TYPE_ORDER` mapping with keys `opening_balance, stock_take, delivery, sale, sales_return, credit_note, debit_note, adjustment`. B creates events of type `sales_return`, `credit_note`, `debit_note`; C relies on this ordering being stable.

- [ ] **Step 1: Write the failing test**

Create `backend/test_ledger_contract.py`:

```python
"""The replay contract three sub-projects build against.

Sub-projects A, B and C are developed concurrently. This file is the tripwire:
if any of them changes replay ordering or gives a money-only event a stock
effect, stock numbers shift silently. Fail loudly here instead.
"""
import unittest

import ledger


SKU = {"sku_id": "s1", "canonical": "Cement", "default_unit": "bag",
       "units": {"bag": 1}}


def _ev(type_, qty, day="2026-01-01"):
    return {"event_id": f"e{type_}{qty}", "sku_id": "s1", "type": type_,
            "qty": qty, "unit": "bag", "occurred_on": day}


class ReplayOrderTests(unittest.TestCase):
    def test_same_day_order_is_baseline_then_in_then_out_then_return(self):
        order = [ledger._TYPE_ORDER[t] for t in
                 ("opening_balance", "delivery", "sale", "sales_return")]
        self.assertEqual(order, sorted(order))

    def test_return_replays_after_the_sale_it_reverses(self):
        events = [_ev("sales_return", 3), _ev("sale", 10), _ev("opening_balance", 100)]
        types = [e["type"] for e in ledger._sorted_events(events)]
        self.assertEqual(types, ["opening_balance", "sale", "sales_return"])

    def test_adjustment_still_replays_last_of_the_known_types(self):
        known = {t: r for t, r in ledger._TYPE_ORDER.items()}
        self.assertEqual(known["adjustment"], max(known.values()))

    def test_unknown_types_sort_after_every_known_type(self):
        unknown_rank = ledger._TYPE_ORDER.get("not_a_real_type", None)
        self.assertIsNone(unknown_rank)
        events = [_ev("mystery", 1), _ev("adjustment", 1)]
        types = [e["type"] for e in ledger._sorted_events(events)]
        self.assertEqual(types, ["adjustment", "mystery"])


class StockEffectTests(unittest.TestCase):
    def test_sales_return_adds_stock_back(self):
        events = [_ev("opening_balance", 100), _ev("sale", 10), _ev("sales_return", 4)]
        self.assertEqual(ledger.stock_at(SKU, events), 94)

    def test_money_only_events_do_not_move_stock(self):
        base = [_ev("opening_balance", 100), _ev("sale", 10)]
        with_notes = base + [_ev("credit_note", 5000), _ev("debit_note", 2000)]
        self.assertEqual(ledger.stock_at(SKU, with_notes),
                         ledger.stock_at(SKU, base))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ../venv/Scripts/python.exe -m unittest test_ledger_contract -v`
Expected: FAIL — `KeyError: 'sales_return'` on the ordering tests, and `test_sales_return_adds_stock_back` returns 90 instead of 94 because the replay loop has no branch for it.

- [ ] **Step 3: Write minimal implementation**

In `backend/ledger.py`, replace `_TYPE_ORDER`:

```python
# within-a-day application order (spec Section 3)
# A same-day return must apply after the sale it reverses. credit_note and
# debit_note are money-only: they get ranks so sorting stays deterministic,
# but deliberately get no branch in the replay loop below, which is what keeps
# them stock-neutral.
_TYPE_ORDER = {"opening_balance": 0, "stock_take": 0, "delivery": 1,
               "sale": 2, "sales_return": 3, "credit_note": 4,
               "debit_note": 4, "adjustment": 5}
_UNKNOWN_TYPE_RANK = 9  # must stay above every known rank
```

Then in `_sorted_events`, change the fallback from the literal `5` — which now
collides with `adjustment` and would sort nondeterministically — to the constant:

```python
def _sorted_events(events: list) -> list:
    return sorted(events, key=lambda e: (_d(e["occurred_on"]),
                                         _TYPE_ORDER.get(e["type"],
                                                         _UNKNOWN_TYPE_RANK)))
```

Then in `_stock_detail`, add one branch after the `sale` branch:

```python
        elif t == "sale":
            qty_base -= q
        elif t == "sales_return":
            qty_base += q
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && ../venv/Scripts/python.exe -m unittest test_ledger_contract -v`
Expected: PASS, 6 tests.

- [ ] **Step 5: Run the existing suite to prove nothing shifted**

Run: `cd backend && ../venv/Scripts/python.exe -m unittest test_agent test_conversation test_store -v 2>&1 | tail -5`
Expected: same pass/fail counts as before the change. Stock maths for existing event types must be untouched.

- [ ] **Step 6: Commit**

```bash
git add backend/ledger.py backend/test_ledger_contract.py
git commit -m "feat(ledger): add return and note event types to the replay contract"
```

---

### Task 2: Idempotent event insertion

**Files:**
- Modify: `backend/sqlrepo.py:110-115` (the `INSERT INTO events` statement)
- Test: `backend/test_ledger_contract.py` (extend)

**Interfaces:**
- Consumes: the existing `UNIQUE (user_id, event_id)` constraint on `events`.
- Produces: inserting an event whose `event_id` already exists is a silent no-op. C's outbox relies on this to resend safely.

- [ ] **Step 1: Write the failing test**

Append to `backend/test_ledger_contract.py`:

```python
class IdempotentInsertTests(unittest.TestCase):
    """An offline outbox resends whatever it could not confirm.

    Without conflict handling the second delivery raises a unique violation and
    the client cannot tell 'already recorded' from 'failed', so it either drops
    a sale or double-posts one.
    """

    def test_insert_statement_ignores_duplicate_event_ids(self):
        import inspect

        import sqlrepo

        source = inspect.getsource(sqlrepo)
        self.assertIn("ON CONFLICT (user_id, event_id) DO NOTHING", source)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ../venv/Scripts/python.exe -m unittest test_ledger_contract.IdempotentInsertTests -v`
Expected: FAIL — the clause is absent.

- [ ] **Step 3: Write minimal implementation**

In `backend/sqlrepo.py`, extend the insert statement:

```python
            conn.execute(
                f"INSERT INTO events (user_id, {', '.join(cols)}) VALUES ("
                + ", ".join(["%s"] * (len(cols) + 1)) + ")"
                + " ON CONFLICT (user_id, event_id) DO NOTHING",
                [self.user_id] + values)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && ../venv/Scripts/python.exe -m unittest test_ledger_contract -v`
Expected: PASS, 7 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/sqlrepo.py backend/test_ledger_contract.py
git commit -m "feat(events): make event insertion idempotent on event_id"
```

---

### Task 3: Schema append — sync column and vertical priors

**Files:**
- Modify: `backend/db.py` (append to the DDL inside `init_schema()`)
- Test: `backend/test_ledger_contract.py` (extend)

**Interfaces:**
- Produces: `events.seq BIGINT` (C assigns it), table `vertical_priors(vertical_id, pack_version, phrase, sku_ref, attributes)` (A writes it, matcher reads it).

- [ ] **Step 1: Write the failing test**

Append to `backend/test_ledger_contract.py`:

```python
class SchemaAppendTests(unittest.TestCase):
    """Three agents append schema concurrently; all of it must be idempotent."""

    def _ddl(self):
        import inspect

        import db

        return inspect.getsource(db)

    def test_events_has_a_sync_sequence_column(self):
        self.assertIn("ALTER TABLE events ADD COLUMN IF NOT EXISTS seq BIGINT",
                      self._ddl())

    def test_vertical_priors_table_exists(self):
        self.assertIn("CREATE TABLE IF NOT EXISTS vertical_priors", self._ddl())

    def test_every_create_table_is_guarded(self):
        ddl = self._ddl()
        self.assertNotIn("CREATE TABLE vertical_priors", ddl)
        self.assertEqual(ddl.count("CREATE TABLE "),
                         ddl.count("CREATE TABLE IF NOT EXISTS "))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ../venv/Scripts/python.exe -m unittest test_ledger_contract.SchemaAppendTests -v`
Expected: FAIL on the first two — neither statement exists yet.

- [ ] **Step 3: Write minimal implementation**

Append to the DDL in `backend/db.py:init_schema()`, after the existing statements:

```sql
-- Offline sync ordering. The client generates event_id as a ULID and the
-- server stamps an authoritative per-tenant sequence on receipt.
ALTER TABLE events ADD COLUMN IF NOT EXISTS seq BIGINT;

-- Vertical packs ship spoken-form priors. Global and versioned, never written
-- by a tenant: a shop's own corrections go to `learning`, which outranks this
-- during resolution.
CREATE TABLE IF NOT EXISTS vertical_priors (
    vertical_id  TEXT NOT NULL,
    pack_version TEXT NOT NULL,
    phrase       TEXT NOT NULL,
    sku_ref      TEXT NOT NULL,
    attributes   JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (vertical_id, pack_version, phrase)
);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && ../venv/Scripts/python.exe -m unittest test_ledger_contract -v`
Expected: PASS, 10 tests.

- [ ] **Step 5: Apply the schema to the dev database**

Run: `cd backend && ../venv/Scripts/python.exe -c "import sarvam_client, db; db.init_schema(); print('ok')"`
Expected: `ok`, and re-running is safe because every statement is guarded.

- [ ] **Step 6: Commit**

```bash
git add backend/db.py backend/test_ledger_contract.py
git commit -m "feat(schema): add event sync sequence and vertical_priors table"
```

---

### Task 4: Vertical config accessors

**Files:**
- Create: `backend/verticals.py`
- Test: `backend/test_verticals.py` (create)

**Interfaces:**
- Consumes: `user_config.data` JSONB, read through the existing repo config accessor.
- Produces: `verticals.tenant_vertical(config: dict) -> tuple[str | None, str | None]` returning `(vertical_id, pack_version)`, and `verticals.set_tenant_vertical(config: dict, vertical_id: str, pack_version: str) -> dict` returning an updated config dict. A builds its loader on top of these; B reads `vertical_id` to decide HSN defaults.

- [ ] **Step 1: Write the failing test**

Create `backend/test_verticals.py`:

```python
import unittest

import verticals


class TenantVerticalTests(unittest.TestCase):
    def test_absent_vertical_reads_as_none(self):
        self.assertEqual(verticals.tenant_vertical({}), (None, None))

    def test_round_trips_through_config(self):
        cfg = verticals.set_tenant_vertical({}, "hardware", "1.0.0")
        self.assertEqual(verticals.tenant_vertical(cfg), ("hardware", "1.0.0"))

    def test_does_not_mutate_the_caller_config(self):
        original = {"shop_name": "Probe Hardware"}
        verticals.set_tenant_vertical(original, "hardware", "1.0.0")
        self.assertNotIn("vertical_id", original)

    def test_preserves_unrelated_config_keys(self):
        cfg = verticals.set_tenant_vertical({"gstin": "27ABCDE1234F1Z5"},
                                            "hardware", "1.0.0")
        self.assertEqual(cfg["gstin"], "27ABCDE1234F1Z5")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ../venv/Scripts/python.exe -m unittest test_verticals -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'verticals'`.

- [ ] **Step 3: Write minimal implementation**

Create `backend/verticals.py`:

```python
"""Vertical pack configuration held per tenant.

A vertical pack is shipped data, not tenant data, so only the pointer to it
lives in `user_config.data`. Sub-project A adds pack loading and seeding on top
of these accessors; keeping them separate means B can ask which vertical a shop
is on without importing the loader.
"""
from __future__ import annotations

VERTICAL_KEY = "vertical_id"
VERSION_KEY = "vertical_pack_version"


def tenant_vertical(config: dict) -> tuple[str | None, str | None]:
    """Return (vertical_id, pack_version) for a tenant, or (None, None)."""
    if not config:
        return (None, None)
    return (config.get(VERTICAL_KEY) or None, config.get(VERSION_KEY) or None)


def set_tenant_vertical(config: dict, vertical_id: str,
                        pack_version: str) -> dict:
    """Return a copy of `config` pointing at a vertical pack.

    Copies rather than mutates: callers pass the live config dict straight from
    the repo, and an in-place edit would half-apply if the write that follows
    fails.
    """
    updated = dict(config or {})
    updated[VERTICAL_KEY] = vertical_id
    updated[VERSION_KEY] = pack_version
    return updated
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && ../venv/Scripts/python.exe -m unittest test_verticals -v`
Expected: PASS, 4 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/verticals.py backend/test_verticals.py
git commit -m "feat(verticals): add per-tenant vertical pack config accessors"
```

---

### Task 5: Frontend section markers

**Files:**
- Modify: `frontend/index.html`
- Test: `backend/test_ledger_contract.py` (extend)

**Interfaces:**
- Produces: four comment fences delimiting regions A, B and C each own exclusively. Agents insert only between a marker and its `end` counterpart.

- [ ] **Step 1: Write the failing test**

Append to `backend/test_ledger_contract.py`:

```python
class FrontendSectionMarkerTests(unittest.TestCase):
    """B and C both edit one 4,600-line file. Markers keep them out of each
    other's regions so merges stay textual rather than semantic."""

    SECTIONS = ("onboarding", "documents", "accounting", "offline")

    def _html(self):
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent
        return (root / "frontend" / "index.html").read_text(encoding="utf-8")

    def test_every_owned_section_is_fenced(self):
        html = self._html()
        for name in self.SECTIONS:
            self.assertIn(f"<!-- @section:{name} -->", html, name)
            self.assertIn(f"<!-- @endsection:{name} -->", html, name)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ../venv/Scripts/python.exe -m unittest test_ledger_contract.FrontendSectionMarkerTests -v`
Expected: FAIL — no markers present.

- [ ] **Step 3: Write minimal implementation**

In `frontend/index.html`, place empty fenced regions. `onboarding` wraps the
existing `#authStepOnboard` block so A extends it in place; the other three are
empty regions added immediately before the closing `</body>`:

```html
<!-- @section:documents -->
<!-- Owned by sub-project B: challan, quotation, proforma, purchase order. -->
<!-- @endsection:documents -->

<!-- @section:accounting -->
<!-- Owned by sub-project B: credit notes, debit notes, returns, price lists. -->
<!-- @endsection:accounting -->

<!-- @section:offline -->
<!-- Owned by sub-project C: service worker, IndexedDB outbox, offline state. -->
<!-- @endsection:offline -->
```

And around the existing onboarding step:

```html
<!-- @section:onboarding -->
          <div id="authStepOnboard" class="hidden">
            ...unchanged...
          </div>
<!-- @endsection:onboarding -->
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && ../venv/Scripts/python.exe -m unittest test_ledger_contract -v`
Expected: PASS, 11 tests.

- [ ] **Step 5: Verify the page still renders**

Run: `cd .. && ./venv/Scripts/python.exe -c "import app; from fastapi.testclient import TestClient; c=TestClient(app.app); r=c.get('/'); print(r.status_code, len(r.text))"`
Expected: `200` and a length close to the previous file size. Comments must not break parsing.

- [ ] **Step 6: Commit**

```bash
git add frontend/index.html backend/test_ledger_contract.py
git commit -m "chore(frontend): fence sections owned by parallel sub-projects"
```

---

## Exit gate

The foundation is done when:

- `cd backend && ../venv/Scripts/python.exe -m unittest test_ledger_contract test_verticals -v` passes (11 + 4 tests).
- The pre-existing suite shows no new failures.
- `db.init_schema()` is idempotent across repeated runs.

Only then may sub-project agents start. They branch from this commit.
