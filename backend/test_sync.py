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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ledger as L
import sync
from repo import JsonRepo


SKU = {"sku_id": "s1", "canonical": "Cement", "family": "cement",
       "default_unit": "bag", "units": {"bag": 1}, "gst_rate": 18}


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


if __name__ == "__main__":
    unittest.main()
