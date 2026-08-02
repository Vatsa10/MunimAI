"""B5 — HSN/SAC per SKU and the e-way bill threshold."""
import unittest
from datetime import date

import hsn
import pdfs


class GstMapLoadingTests(unittest.TestCase):
    def test_loads_the_hardware_pack_gst_map(self):
        gm = hsn.load_gst_map("hardware")
        self.assertIsNotNone(gm)
        self.assertEqual(gm["categories"]["cement"]["hsn"], "2523")
        self.assertEqual(gm["categories"]["cement"]["gst_rate"], 18)

    def test_no_vertical_id_returns_none(self):
        self.assertIsNone(hsn.load_gst_map(None))
        self.assertIsNone(hsn.load_gst_map(""))

    def test_unknown_vertical_returns_none_rather_than_raising(self):
        self.assertIsNone(hsn.load_gst_map("does_not_exist"))

    def test_no_gst_rate_in_the_pack_is_ever_28_or_12(self):
        gm = hsn.load_gst_map("hardware")
        rates = {c["gst_rate"] for c in gm["categories"].values()}
        self.assertNotIn(28, rates)
        self.assertNotIn(12, rates)


class HsnForSkuTests(unittest.TestCase):
    def test_skus_own_hsn_wins(self):
        sku = {"family": "cement", "attributes": {"hsn": "9999"}}
        gm = hsn.load_gst_map("hardware")
        self.assertEqual(hsn.hsn_for_sku(sku, gm), "9999")

    def test_falls_back_to_the_vertical_packs_category_default(self):
        sku = {"family": "tmt", "attributes": {}}
        gm = hsn.load_gst_map("hardware")
        self.assertEqual(hsn.hsn_for_sku(sku, gm), "7214")

    def test_degrades_to_blank_with_no_vertical_pack_loaded(self):
        sku = {"family": "cement", "attributes": {}}
        self.assertEqual(hsn.hsn_for_sku(sku, None), "")

    def test_degrades_to_blank_for_an_unmapped_family(self):
        sku = {"family": "nails", "attributes": {}}
        gm = hsn.load_gst_map("hardware")
        self.assertEqual(hsn.hsn_for_sku(sku, gm), "")


class EwayBillThresholdTests(unittest.TestCase):
    def test_over_fifty_thousand_requires_eway_bill(self):
        self.assertTrue(hsn.eway_bill_required(50001))

    def test_exactly_fifty_thousand_does_not_require_it(self):
        self.assertFalse(hsn.eway_bill_required(50000))

    def test_under_threshold_does_not_require_it(self):
        self.assertFalse(hsn.eway_bill_required(1200))


class BillPdfHsnAndEwayTests(unittest.TestCase):
    def test_bill_pdf_accepts_hsn_per_line_and_eway_bill_no(self):
        pdf = pdfs.bill_pdf(
            shop="Probe Hardware", owner="Ramesh", customer={"name": "Site"},
            lines=[{"name": "Cement", "qty": 200, "unit": "bag", "rate": 380,
                    "amount": 76000, "hsn": "2523"}],
            subtotal=76000, gst=13680, total=89680, bill_no="B-0009",
            on=date(2026, 8, 2), payment="credit", eway_bill_no="EWB1234567890")
        self.assertTrue(pdf.startswith(b"%PDF"))

    def test_bill_pdf_still_renders_with_no_hsn_or_eway_data(self):
        pdf = pdfs.bill_pdf(
            shop="Probe Hardware", owner="Ramesh", customer={"name": "Walk-in"},
            lines=[{"name": "Cement", "qty": 2, "unit": "bag", "rate": 380,
                    "amount": 760}],
            subtotal=760, gst=137, total=897, bill_no="B-0010",
            on=date(2026, 8, 2), payment="cash")
        self.assertTrue(pdf.startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
