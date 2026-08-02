"""B2 — Tally/Busy XML export."""
import unittest
import xml.etree.ElementTree as ET

import tally_export

CATALOGUE = {"s1": {"sku_id": "s1", "canonical": "UltraTech PPC Cement 50kg"}}
CUSTOMERS = {"cust_0001": {"customer_id": "cust_0001", "name": "Site Office"}}


def _ev(type_, **kw):
    base = {"event_id": "evt_0001", "type": type_, "sku_id": "s1", "qty": 10,
           "unit": "bag", "rate": 380, "quoted_rate": 380,
           "occurred_on": "2026-08-02"}
    base.update(kw)
    return base


class TallyXmlStructureTests(unittest.TestCase):
    def test_root_is_envelope_with_import_request(self):
        xml = tally_export.build_tally_xml(
            events=[_ev("sale")], payments=[], catalogue_by_id=CATALOGUE,
            customers_by_id=CUSTOMERS)
        root = ET.fromstring(xml)
        self.assertEqual(root.tag, "ENVELOPE")
        self.assertEqual(root.findtext("HEADER/TALLYREQUEST"), "Import Data")

    def test_covers_sales_purchases_returns_notes_and_payments(self):
        events = [
            _ev("sale", event_id="evt_0001"),
            _ev("delivery", event_id="evt_0002"),
            _ev("sales_return", event_id="evt_0003"),
            _ev("credit_note", event_id="evt_0004"),
            _ev("debit_note", event_id="evt_0005"),
        ]
        payments = [{"payment_id": "pay_0001", "customer_id": "cust_0001",
                    "amount": 5000, "paid_on": "2026-08-02"}]
        xml = tally_export.build_tally_xml(
            events=events, payments=payments, catalogue_by_id=CATALOGUE,
            customers_by_id=CUSTOMERS)
        root = ET.fromstring(xml)
        vouchers = root.findall(".//VOUCHER")
        self.assertEqual(len(vouchers), 6)
        types = {v.get("VCHTYPE") for v in vouchers}
        self.assertEqual(types, {"Sales", "Purchase", "Credit Note",
                                 "Debit Note", "Receipt"})

    def test_stock_neutral_note_still_carries_the_ledger_amount(self):
        xml = tally_export.build_tally_xml(
            events=[_ev("credit_note", qty=1, rate=5000, quoted_rate=5000,
                       customer_id="cust_0001")],
            payments=[], catalogue_by_id=CATALOGUE, customers_by_id=CUSTOMERS)
        root = ET.fromstring(xml)
        amount = root.findtext(".//ALLLEDGERENTRIES.LIST/AMOUNT")
        self.assertEqual(amount, "5000.0")

    def test_party_name_falls_back_to_cash_customer(self):
        xml = tally_export.build_tally_xml(
            events=[_ev("sale", customer_id=None)], payments=[],
            catalogue_by_id=CATALOGUE, customers_by_id=CUSTOMERS)
        root = ET.fromstring(xml)
        self.assertEqual(root.findtext(".//PARTYLEDGERNAME"), "Cash Customer")

    def test_unrelated_event_types_are_excluded(self):
        xml = tally_export.build_tally_xml(
            events=[_ev("opening_balance"), _ev("stock_take"), _ev("adjustment")],
            payments=[], catalogue_by_id=CATALOGUE, customers_by_id=CUSTOMERS)
        root = ET.fromstring(xml)
        self.assertEqual(root.findall(".//VOUCHER"), [])


class AccountingEventEndpointsTests(unittest.TestCase):
    def test_endpoints_are_registered(self):
        import main
        paths = {route.path for route in main.app.routes}
        for p in ("/api/accounting/sales-return", "/api/accounting/credit-note",
                  "/api/accounting/debit-note", "/api/accounting/tally-export"):
            self.assertIn(p, paths, p)


if __name__ == "__main__":
    unittest.main()
