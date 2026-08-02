# Sub-project B — Parity Pack Implementation Plan

> Builds on the foundation contract (`docs/superpowers/plans/2026-08-02-foundation-contract.md`)
> and the design (`docs/superpowers/specs/2026-08-02-vertical-packs-parity-offline-design.md`
> section 4). Executed task-by-task, TDD, one commit per task.

## Global constraints (repeat of the brief)

- Tests: `cd backend && DATABASE_URL= PYTHONIOENCODING=utf-8 <venv>/python.exe -m unittest discover -s . -p 'test_*.py'`.
  Baseline in this worktree: 222 passing. Never regress it.
- Never use bare `python`; always the venv interpreter.
- `_TYPE_ORDER`, `_sorted_events`, `_stock_detail` in `backend/ledger.py` are frozen. Only
  create events of type `sales_return`, `credit_note`, `debit_note`.
- `backend/sqlrepo.py` and existing statements in `backend/db.py` are frozen. New DDL is
  appended, idempotent (`CREATE TABLE IF NOT EXISTS`, `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`).
- `frontend/index.html` may only be edited between `<!-- @section:documents -->` /
  `<!-- @endsection:documents -->` and `<!-- @section:accounting -->` / `<!-- @endsection:accounting -->`.
- No test may hit a live database.
- No Claude attribution in commits.

## Task order

1. **B1 Documents** — delivery challan, quotation, proforma invoice, purchase order PDFs,
   built on `backend/pdfs.py` + `backend/documents.py`. One test per doc type asserting the
   PDF renders and totals match input.
2. **B2 Accounting events + Tally export** — endpoints creating `sales_return`, `credit_note`,
   `debit_note` events through the existing repo/ledger path; XML export of sales, purchases,
   returns, notes, payments for a date range.
3. **B3 Import + price lists** — bulk Excel/CSV catalogue import with dry-run preview
   (created vs. updated, no writes until commit); per-SKU multi-rate price list
   (retail/contractor/dealer), customer carries default tier.
4. **B4 Roles + print** — owner/manager/staff roles enforced server-side in auth middleware;
   thermal 58/80mm and A4 print layouts.
5. **B5 HSN/SAC + e-way bill** — HSN per SKU in `skus.attributes` JSONB, read from
   `verticals/hardware/gst_map.yaml` if present else blank; e-way bill threshold surfaced +
   bill number captured on invoices >Rs 50,000.

Each task: write failing test(s) first, minimal implementation, run full suite, commit.

## Exit criteria

- Full backend suite green, count >= 222 (plus new tests).
- One test per document type (B1).
- Tally XML export test validates structure (B2).
- Import dry-run test asserts no writes before commit (B3).
- Permissions test asserts server-side enforcement per role (B4).
- HSN degrades to blank without a vertical pack; e-way bill flag test (B5).
