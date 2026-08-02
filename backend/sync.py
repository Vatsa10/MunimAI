"""sync.py — offline outbox apply and compact snapshot (spec section 5.3-5.4).

The offline client writes events locally with a client-generated ULID
`event_id` and posts the whole outbox on reconnect. `apply_outbox` is the
server side of that: dedupe by `event_id` (mirroring the
`UNIQUE (user_id, event_id)` / `ON CONFLICT ... DO NOTHING` guarantee already
built into `sqlrepo.py`, so a resend of a partially-delivered outbox is always
safe) and stamp a monotonic per-tenant `seq` on whatever is genuinely new.

`snapshot` ships the compact stock/dues state the client replays local
unsynced events on top of. It is deliberately thin: it calls into
`ledger._stock_detail` and `crm.accounts` for the actual numbers rather than
re-deriving them, because this module must never become a second
implementation of replay maths (spec 5.4 — that is how two implementations of
stock arithmetic quietly diverge).
"""
from __future__ import annotations

import crm
import clock
import ledger as L


def _existing_event_ids(repo) -> set:
    return {e.get("event_id") for e in repo.all_events() if e.get("event_id")}


def _next_seq(repo) -> int:
    seqs = [e.get("seq") for e in repo.all_events() if isinstance(e.get("seq"), (int, float))]
    return int(max(seqs)) + 1 if seqs else 1


# Baseline event types (spec Section 3 / ledger._TYPE_ORDER): a stock_take and
# an opening_balance both overwrite the running qty rather than accumulate, so
# they conflict with each other the same way two stock_takes do.
_BASELINE_TYPES = ("opening_balance", "stock_take")

_AUDIT_DOC = "product_edit_audit.json"


def _audit_event_ids(repo) -> set:
    store = getattr(repo, "_store", None)
    if store is not None:
        return {r.get("event_id") for r in store.read(_AUDIT_DOC, [])
                if r.get("event_id")}
    user_id = getattr(repo, "user_id", None)
    if user_id is None:
        return set()
    import db
    with db.connect() as conn:
        cur = conn.execute(
            "SELECT event_id FROM product_edit_audit WHERE user_id = %s",
            (user_id,))
        return {row[0] for row in cur.fetchall()}


def _write_audit_row(repo, row: dict) -> None:
    store = getattr(repo, "_store", None)
    if store is not None:
        def _append(rows):
            rows.append(row)
            return None
        store.mutate(_AUDIT_DOC, [], _append)
        return
    user_id = getattr(repo, "user_id", None)
    if user_id is None:
        return
    import json
    import db
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO product_edit_audit (user_id, audit_id, sku_id,"
            " event_id, edited_at, old_value, new_value)"
            " VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)",
            (user_id, row["audit_id"], row["sku_id"], row["event_id"],
             row["edited_at"],
             json.dumps(row["old_value"], ensure_ascii=False),
             json.dumps(row["new_value"], ensure_ascii=False)))


def _apply_product_edit(repo, ev: dict) -> None:
    """Spec 5.5: product edits are last write wins, with an audit row.

    "Last write wins" falls out of processing the outbox in order and simply
    overwriting the catalogue row; the audit row is what makes that
    non-destructive to inspect later.
    """
    sku_id = ev.get("sku_id")
    current = repo.sku(sku_id) or {}
    patch = ev.get("patch") or {}
    updated = {**current, **patch, "sku_id": sku_id}
    _write_audit_row(repo, {
        "audit_id": ev["event_id"],
        "event_id": ev["event_id"],
        "sku_id": sku_id,
        "edited_at": ev.get("occurred_at") or clock.today().isoformat(),
        "old_value": current,
        "new_value": updated,
    })
    repo.upsert_sku(updated)


def _loses_stock_take_conflict(repo, ev: dict) -> bool:
    """Spec 5.5: stock takes resolve by timestamp.

    A baseline event (stock_take/opening_balance) carries the client's real
    `occurred_at` timestamp of when the count was actually taken, distinct
    from `occurred_on` (just the day). If a baseline already recorded for the
    same sku+day has a *later* timestamp than this incoming one, the incoming
    one is stale and must not become the effective count — otherwise whichever
    outbox happens to sync last would silently win instead of whichever count
    was actually taken last.
    """
    ts = ev.get("occurred_at")
    if not ts:
        return False
    for e in repo.all_events():
        if (e.get("type") in _BASELINE_TYPES
                and e.get("sku_id") == ev.get("sku_id")
                and e.get("occurred_on") == ev.get("occurred_on")
                and e.get("occurred_at")
                and e["occurred_at"] > ts):
            return True
    return False


def _write_through_pipeline(repo, ev: dict, eid: str, seq: int) -> None:
    """Route one outbox event through the same write pipeline the online path
    uses, so an offline sale gets rate-unit conversion, confidence scoring and
    cost-based rate assumption too (spec gap closed here).

    `main` is imported lazily, matching the pattern conversation.py uses
    everywhere it calls into `_write_events` — see main.py's comment above
    `sys.modules.setdefault("main", ...)` for the double-module-import hazard
    a top-level `import main` would otherwise hit.

    `main._write_events` reads/writes through the module-level `repo` proxy,
    not a parameter, so the proxy's ContextVar is pointed at the caller's repo
    for the duration of the call (the same mechanism test_sync.py's
    `_signed_in` helper uses for the HTTP-route tests).

    `_write_events` never copies a caller-supplied event_id onto the event it
    builds — it always mints a fresh one via `repo.append_event`. Left alone
    that would silently drop the client's ULID and break the outbox's
    idempotency guarantee on resend, so `repo.append_event` is wrapped for the
    duration of this call to stamp the client's event_id (and our sync seq)
    onto the event before it is persisted.
    """
    import main

    # `repo` here may already BE `main.repo` (the request-scoped proxy, as it
    # is when this runs through the /api/sync/outbox route) or a raw repo (as
    # in the unit tests, which call sync.apply_outbox directly against a
    # JsonRepo). Only the latter needs the proxy's ContextVar redirected —
    # doing it unconditionally would point the proxy's ContextVar AT the
    # proxy itself and recurse forever through `_RepoProxy.__getattr__`.
    is_proxy = repo is main.repo

    original_append = repo.append_event

    def _append_with_client_identity(event, _orig=original_append):
        event["event_id"] = eid
        event["seq"] = seq
        # _write_events always sets occurred_at to None (it is unused on the
        # online path); the offline client's real capture timestamp is what
        # stock-take conflict resolution above compares on, so it must
        # survive the pipeline the same way event_id and seq do.
        if ev.get("occurred_at"):
            event["occurred_at"] = ev["occurred_at"]
        return _orig(event)

    repo.append_event = _append_with_client_identity
    token = None if is_proxy else main._CURRENT.set(repo)
    try:
        item = dict(ev)
        main._write_events(
            ev.get("type"), [item],
            ev.get("occurred_on"), ev.get("precision", "exact"),
            ev.get("source", "offline_outbox"))
    finally:
        if token is not None:
            main._CURRENT.reset(token)
        del repo.append_event


def apply_outbox(repo, events: list) -> dict:
    """Apply a client outbox. Idempotent: replaying the same list is a no-op.

    Returns {"results": [{"event_id", "status", "seq"?, "reason"?}, ...]},
    one entry per input event, in order.
    """
    known_ids = _existing_event_ids(repo) | _audit_event_ids(repo)
    next_seq = _next_seq(repo)
    results = []
    for ev in events:
        eid = ev.get("event_id")
        if not eid:
            results.append({"event_id": None, "status": "rejected",
                            "reason": "missing event_id"})
            continue
        if eid in known_ids:
            results.append({"event_id": eid, "status": "duplicate"})
            continue

        etype = ev.get("type")

        if etype == "product_edit":
            _apply_product_edit(repo, ev)
            known_ids.add(eid)
            results.append({"event_id": eid, "status": "accepted", "seq": next_seq})
            next_seq += 1
            continue

        if etype in _BASELINE_TYPES and _loses_stock_take_conflict(repo, ev):
            results.append({"event_id": eid, "status": "conflict_superseded"})
            continue

        seq_for_this = next_seq
        _write_through_pipeline(repo, ev, eid, seq_for_this)
        set_seq = getattr(repo, "set_event_seq", None)
        if callable(set_seq):
            # Postgres path: the INSERT statement is untouched (spec/plan
            # constraint), so seq lands via a separate UPDATE instead.
            set_seq(eid, seq_for_this)
        known_ids.add(eid)
        results.append({"event_id": eid, "status": "accepted", "seq": seq_for_this})
        next_seq += 1
    return {"results": results}


def _stock_snapshot(repo) -> dict:
    events = repo.all_events()
    out = {}
    for sku in repo.load_catalogue():
        det = L._stock_detail(sku, events)
        if det["qty"] == L.UNCOUNTED:
            out[sku["sku_id"]] = {"uncounted": True,
                                  "unit": sku.get("default_unit")}
        else:
            out[sku["sku_id"]] = {"uncounted": False, "qty": det["qty"],
                                  "unit": det.get("unit", sku.get("default_unit"))}
    return out


def _dues_snapshot(repo) -> dict:
    out = {}
    for account in crm.accounts(repo):
        out[account["customer_id"]] = {
            "name": account.get("name") or "",
            "phone": account.get("phone") or "",
            "outstanding": account.get("outstanding", 0),
        }
    return out


def snapshot(repo) -> dict:
    """Compact stock/dues state a client replays its own outbox on top of."""
    seqs = [e.get("seq") for e in repo.all_events()
            if isinstance(e.get("seq"), (int, float))]
    return {
        "as_of": clock.today().isoformat(),
        "seq": int(max(seqs)) if seqs else 0,
        "stock": _stock_snapshot(repo),
        "dues": _dues_snapshot(repo),
    }
