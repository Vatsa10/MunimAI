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
        self.assertIsNone(ledger._TYPE_ORDER.get("not_a_real_type"))
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


class SchemaAppendTests(unittest.TestCase):
    """Three agents append schema concurrently; all of it must be idempotent."""

    def _ddl(self):
        import db

        return db.SCHEMA

    def test_events_has_a_sync_sequence_column(self):
        self.assertIn("ALTER TABLE events ADD COLUMN IF NOT EXISTS seq BIGINT",
                      self._ddl())

    def test_vertical_priors_table_exists(self):
        self.assertIn("CREATE TABLE IF NOT EXISTS vertical_priors", self._ddl())

    def test_every_create_table_is_guarded(self):
        ddl = self._ddl()
        self.assertEqual(ddl.count("CREATE TABLE "),
                         ddl.count("CREATE TABLE IF NOT EXISTS "))


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


if __name__ == "__main__":
    unittest.main()
