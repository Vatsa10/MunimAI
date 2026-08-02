"""Offline outbox sync: idempotent apply + compact snapshot for delta replay.

Sub-project C (spec section 5). The round-trip test at the bottom is the one
the design doc requires: queue events offline, reconnect, assert server state
matches, and that resending the same outbox a second time is a no-op — that
is what proves the ON CONFLICT idempotency guarantee end to end.

Runs entirely against a temp-dir JsonRepo. No live database.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient

import ledger as L
import main
import sync
from repo import JsonRepo


SKU = {"sku_id": "s1", "canonical": "Cement", "family": "cement",
       "default_unit": "bag", "units": {"bag": 1}, "gst_rate": 18}

PRICED_SKU = {"sku_id": "s1", "canonical": "Cement", "family": "cement",
              "default_unit": "bag", "units": {"bag": 1}, "gst_rate": 18,
              "opening_cost_per_kg": 300}


def _repo(tmp_dir: str) -> JsonRepo:
    r = JsonRepo(Path(tmp_dir))
    r.upsert_sku(SKU)
    return r


def _ev(event_id: str, type_: str, qty: float, day: str = "2026-08-01") -> dict:
    return {"event_id": event_id, "type": type_, "sku_id": "s1", "qty": qty,
            "unit": "bag", "occurred_on": day, "precision": "exact",
            "source": "offline_outbox"}


class ApplyOutboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = _repo(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_accepts_new_events_and_assigns_increasing_seq(self):
        out = sync.apply_outbox(self.repo, [
            _ev("ulid_a", "opening_balance", 100),
            _ev("ulid_b", "sale", 10),
        ])
        statuses = [r["status"] for r in out["results"]]
        self.assertEqual(statuses, ["accepted", "accepted"])
        seqs = [r["seq"] for r in out["results"]]
        self.assertEqual(seqs, sorted(seqs))
        self.assertEqual(len(set(seqs)), 2)

    def test_missing_event_id_is_rejected_not_appended(self):
        out = sync.apply_outbox(self.repo, [{"type": "sale", "sku_id": "s1",
                                              "qty": 1, "unit": "bag",
                                              "occurred_on": "2026-08-01"}])
        self.assertEqual(out["results"][0]["status"], "rejected")
        self.assertEqual(self.repo.all_events(), [])

    def test_resending_the_same_outbox_is_a_no_op(self):
        outbox = [_ev("ulid_a", "opening_balance", 100),
                  _ev("ulid_b", "sale", 10)]
        sync.apply_outbox(self.repo, outbox)
        before = len(self.repo.all_events())

        again = sync.apply_outbox(self.repo, outbox)

        self.assertEqual([r["status"] for r in again["results"]],
                         ["duplicate", "duplicate"])
        self.assertEqual(len(self.repo.all_events()), before)

    def test_duplicate_within_a_single_call_is_also_a_no_op(self):
        outbox = [_ev("ulid_a", "delivery", 5), _ev("ulid_a", "delivery", 5)]
        out = sync.apply_outbox(self.repo, outbox)
        self.assertEqual([r["status"] for r in out["results"]],
                         ["accepted", "duplicate"])
        self.assertEqual(len(self.repo.all_events()), 1)


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = _repo(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_uncounted_sku_reports_uncounted(self):
        snap = sync.snapshot(self.repo)
        self.assertTrue(snap["stock"]["s1"]["uncounted"])

    def test_snapshot_reflects_committed_events(self):
        sync.apply_outbox(self.repo, [_ev("ulid_a", "opening_balance", 100),
                                      _ev("ulid_b", "sale", 10)])
        snap = sync.snapshot(self.repo)
        self.assertEqual(snap["stock"]["s1"]["qty"], 90)
        self.assertEqual(snap["stock"]["s1"]["unit"], "bag")
        self.assertIn("seq", snap)
        self.assertIn("as_of", snap)
        self.assertIn("dues", snap)


class OfflineRoundTripTests(unittest.TestCase):
    """The required test: queue offline, reconnect, verify state + no-op resend."""

    def test_offline_round_trip_matches_server_state_and_resend_is_a_no_op(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _repo(tmp)

            # Client was offline and queued these with its own ULIDs.
            queued_outbox = [
                _ev("01HXA0000000000000000001", "opening_balance", 100),
                _ev("01HXA0000000000000000002", "delivery", 20),
                _ev("01HXA0000000000000000003", "sale", 30),
            ]

            # Reconnect: post the whole outbox once.
            first = sync.apply_outbox(repo, queued_outbox)
            self.assertEqual([r["status"] for r in first["results"]],
                             ["accepted"] * 3)
            self.assertEqual(L.stock_at(SKU, repo.all_events()), 90)
            events_after_first = len(repo.all_events())

            # A flaky connection resends the same outbox wholesale.
            second = sync.apply_outbox(repo, queued_outbox)
            self.assertEqual([r["status"] for r in second["results"]],
                             ["duplicate"] * 3)
            self.assertEqual(len(repo.all_events()), events_after_first)
            self.assertEqual(L.stock_at(SKU, repo.all_events()), 90)


class OfflineWritePipelineTests(unittest.TestCase):
    """The offline outbox must go through main._write_events, not a raw
    repo.append_event — otherwise offline sales skip rate-unit conversion,
    confidence scoring and cost-based rate assumption (spec 5.3/5.4)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = JsonRepo(Path(self.tmp.name))
        self.repo.upsert_sku(PRICED_SKU)

    def tearDown(self):
        self.tmp.cleanup()

    def test_offline_sale_with_no_rate_is_auto_priced_like_the_online_path(self):
        # Establish a baseline so the sale isn't UNCOUNTED.
        sync.apply_outbox(self.repo, [_ev("ulid_open", "opening_balance", 100)])

        outbox_ev = _ev("ulid_sale", "sale", 5)
        outbox_ev.pop("unit", None)
        outbox_ev["unit"] = "bag"
        # No rate/rate_unit supplied, as the offline client never asked one.
        sync.apply_outbox(self.repo, [outbox_ev])

        stored = next(e for e in self.repo.all_events()
                     if e["event_id"] == "ulid_sale")

        token = main._CURRENT.set(self.repo)
        try:
            online = main._write_events(
                "sale", [{"sku_id": "s1", "qty": 5, "unit": "bag"}],
                "2026-08-01", "exact", "voice_live")
        finally:
            main._CURRENT.reset(token)
        expected_rate = online["committed"][0]["rate"]

        self.assertIsNotNone(stored.get("quoted_rate"))
        self.assertEqual(stored["quoted_rate"], expected_rate)
        self.assertIsNotNone(stored.get("confidence"))

    def test_resent_outbox_is_still_a_no_op_after_pipeline_change(self):
        outbox = [_ev("ulid_open", "opening_balance", 100),
                  _ev("ulid_sale", "sale", 5)]
        sync.apply_outbox(self.repo, outbox)
        before = list(self.repo.all_events())

        again = sync.apply_outbox(self.repo, outbox)

        self.assertEqual([r["status"] for r in again["results"]],
                         ["duplicate", "duplicate"])
        self.assertEqual(self.repo.all_events(), before)
        # The client's ULID must survive the pipeline, or dedupe breaks.
        ids = {e["event_id"] for e in self.repo.all_events()}
        self.assertEqual(ids, {"ulid_open", "ulid_sale"})

    def test_offline_sale_still_moves_stock(self):
        sync.apply_outbox(self.repo, [_ev("ulid_open", "opening_balance", 100),
                                      _ev("ulid_sale", "sale", 5)])
        self.assertEqual(L.stock_at(PRICED_SKU, self.repo.all_events()), 95)


class ConflictResolutionTests(unittest.TestCase):
    """Spec 5.5: stock takes resolve by timestamp; product edits are last
    write wins with an audit row."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = _repo(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_stock_take_conflict_resolves_by_timestamp(self):
        older = _ev("ulid_older", "stock_take", 50)
        older["occurred_at"] = "2026-08-01T09:00:00"
        newer = _ev("ulid_newer", "stock_take", 80)
        newer["occurred_at"] = "2026-08-01T18:00:00"

        # The newer count syncs first (its device reconnected sooner)...
        sync.apply_outbox(self.repo, [newer])
        # ...then the older, delayed count arrives afterwards.
        out = sync.apply_outbox(self.repo, [older])

        self.assertEqual(out["results"][0]["status"], "conflict_superseded")
        self.assertEqual(L.stock_at(SKU, self.repo.all_events()), 80)

    def test_stock_take_conflict_lets_the_later_timestamp_win_regardless_of_order(self):
        older = _ev("ulid_older", "stock_take", 50)
        older["occurred_at"] = "2026-08-01T09:00:00"
        newer = _ev("ulid_newer", "stock_take", 80)
        newer["occurred_at"] = "2026-08-01T18:00:00"

        # This time the older one happens to sync first.
        sync.apply_outbox(self.repo, [older])
        out = sync.apply_outbox(self.repo, [newer])

        self.assertEqual(out["results"][0]["status"], "accepted")
        self.assertEqual(L.stock_at(SKU, self.repo.all_events()), 80)

    def test_product_edit_writes_an_audit_row(self):
        edit = {"event_id": "ulid_edit", "type": "product_edit", "sku_id": "s1",
                "patch": {"canonical": "Cement (Super Fine)"},
                "occurred_at": "2026-08-01T10:00:00"}

        sync.apply_outbox(self.repo, [edit])

        self.assertEqual(self.repo.sku("s1")["canonical"], "Cement (Super Fine)")
        rows = self.repo._store.read("product_edit_audit.json", [])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["sku_id"], "s1")
        self.assertEqual(rows[0]["old_value"]["canonical"], "Cement")
        self.assertEqual(rows[0]["new_value"]["canonical"], "Cement (Super Fine)")

    def test_product_edit_resend_is_a_no_op(self):
        edit = {"event_id": "ulid_edit", "type": "product_edit", "sku_id": "s1",
                "patch": {"canonical": "Cement (Super Fine)"},
                "occurred_at": "2026-08-01T10:00:00"}
        sync.apply_outbox(self.repo, [edit])
        out = sync.apply_outbox(self.repo, [edit])
        self.assertEqual(out["results"][0]["status"], "duplicate")
        rows = self.repo._store.read("product_edit_audit.json", [])
        self.assertEqual(len(rows), 1)


class ConcurrentOutboxTests(unittest.TestCase):
    """/api/sync/outbox passes `main.repo` — a module-level singleton — into
    apply_outbox, and `sync_outbox` is a sync `def`, so FastAPI runs
    concurrent requests against it in a threadpool. Nothing in the write
    pipeline may mutate that shared object for the duration of one call, or
    one tenant's request can stamp its identity onto another tenant's event
    (and `del repo.append_event` in a finally block can race another
    thread's own delete). This reproduces that path directly with real
    threads instead of going through TestClient, so a slow-but-real race
    window is exercised rather than one thread completing before the next
    starts."""

    def test_concurrent_outbox_calls_do_not_cross_contaminate_event_ids(self):
        import threading

        rounds = 25
        errors = []

        for _ in range(rounds):
            with tempfile.TemporaryDirectory() as tmp_a, \
                 tempfile.TemporaryDirectory() as tmp_b:
                repo_a = _repo(tmp_a)
                repo_b = _repo(tmp_b)
                barrier = threading.Barrier(2)

                def _run(target_repo, eid):
                    token = main._CURRENT.set(target_repo)
                    try:
                        barrier.wait(timeout=5)
                        sync.apply_outbox(
                            main.repo, [_ev(eid, "opening_balance", 100)])
                    except Exception as e:  # pragma: no cover - surfaced below
                        errors.append(e)
                    finally:
                        main._CURRENT.reset(token)

                t1 = threading.Thread(target=_run, args=(repo_a, "ulid_a"))
                t2 = threading.Thread(target=_run, args=(repo_b, "ulid_b"))
                t1.start()
                t2.start()
                t1.join()
                t2.join()

                self.assertEqual(errors, [])
                ids_a = {e["event_id"] for e in repo_a.all_events()}
                ids_b = {e["event_id"] for e in repo_b.all_events()}
                self.assertEqual(ids_a, {"ulid_a"},
                                 "shop A's event lost/gained an id under concurrency")
                self.assertEqual(ids_b, {"ulid_b"},
                                 "shop B's event lost/gained an id under concurrency")


USER = {"user_id": "u_offline", "phone": "+919999999998", "name": "Owner",
        "shop_name": "Offline Traders"}


@contextmanager
def _signed_in(repo):
    """Route the session middleware to a temp-dir JsonRepo, no live DB."""
    def _bind(user):
        main._CURRENT_USER.set(user)
        main._CURRENT.set(repo)

    with patch.object(main.auth, "user_for_token", return_value=USER), \
            patch.object(main, "bind_user", side_effect=_bind):
        yield TestClient(main.app)


class SyncRoutesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = _repo(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_outbox_route_applies_and_reports_per_event_status(self):
        with _signed_in(self.repo) as client:
            resp = client.post(
                "/api/sync/outbox",
                headers={"Authorization": "Bearer x"},
                json={"events": [_ev("ulid_1", "opening_balance", 50)]})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["results"][0]["status"], "accepted")

    def test_outbox_route_is_a_no_op_on_resend(self):
        outbox = {"events": [_ev("ulid_1", "opening_balance", 50)]}
        with _signed_in(self.repo) as client:
            client.post("/api/sync/outbox", headers={"Authorization": "Bearer x"},
                       json=outbox)
            resp = client.post("/api/sync/outbox",
                               headers={"Authorization": "Bearer x"}, json=outbox)
        self.assertEqual(resp.json()["results"][0]["status"], "duplicate")

    def test_snapshot_route_requires_a_session(self):
        with _signed_in(self.repo) as client:
            pass  # exits the patch context before the unauthenticated call
        resp = client.get("/api/sync/snapshot")
        self.assertEqual(resp.status_code, 401)

    def test_snapshot_route_returns_stock_and_dues(self):
        with _signed_in(self.repo) as client:
            client.post("/api/sync/outbox", headers={"Authorization": "Bearer x"},
                       json={"events": [_ev("ulid_1", "opening_balance", 50)]})
            resp = client.get("/api/sync/snapshot",
                              headers={"Authorization": "Bearer x"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["stock"]["s1"]["qty"], 50)
        self.assertIn("dues", body)


class PwaShellRoutesTests(unittest.TestCase):
    """The service worker and manifest must be fetchable with no session —
    that is the entire point of an installable offline shell."""

    def test_service_worker_is_served_from_the_root_scope(self):
        client = TestClient(main.app)
        resp = client.get("/sw.js")
        self.assertEqual(resp.status_code, 200)

    def test_manifest_is_served_unauthenticated(self):
        client = TestClient(main.app)
        resp = client.get("/manifest.webmanifest")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("start_url", resp.json())


if __name__ == "__main__":
    unittest.main()
