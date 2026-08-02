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


def apply_outbox(repo, events: list) -> dict:
    """Apply a client outbox. Idempotent: replaying the same list is a no-op.

    Returns {"results": [{"event_id", "status", "seq"?, "reason"?}, ...]},
    one entry per input event, in order.
    """
    known_ids = _existing_event_ids(repo)
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
        stored = dict(ev)
        stored["seq"] = next_seq
        repo.append_event(stored)
        set_seq = getattr(repo, "set_event_seq", None)
        if callable(set_seq):
            # Postgres path: the INSERT statement is untouched (spec/plan
            # constraint), so seq lands via a separate UPDATE instead.
            set_seq(eid, next_seq)
        known_ids.add(eid)
        results.append({"event_id": eid, "status": "accepted", "seq": next_seq})
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
