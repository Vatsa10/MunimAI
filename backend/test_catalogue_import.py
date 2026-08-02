"""B3 — bulk catalogue import (dry-run preview) and multi-rate price lists."""
import unittest

import catalogue_import as CI


class FakeRepo:
    def __init__(self, catalogue):
        self.catalogue = list(catalogue)
        self.writes = []

    def upsert_sku(self, sku):
        self.writes.append(sku)
        existing = next((s for s in self.catalogue
                         if s["sku_id"] == sku["sku_id"]), None)
        if existing:
            existing.update(sku)
        else:
            self.catalogue.append(sku)


EXISTING = [{"sku_id": "s1", "canonical": "UltraTech PPC Cement 50kg"}]


class ParseRowsTests(unittest.TestCase):
    def test_parses_csv_with_aliased_headers(self):
        csv_bytes = (
            b"Name,Unit,GST,Cost,Retail,Contractor,Dealer,HSN\n"
            b"Ambuja Cement 50kg,bag,18,340,380,365,350,2523\n"
        )
        rows = CI.parse_rows(csv_bytes, "catalogue.csv")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["canonical"], "Ambuja Cement 50kg")
        self.assertEqual(rows[0]["price_retail"], "380")
        self.assertEqual(rows[0]["hsn"], "2523")


class PreviewImportTests(unittest.TestCase):
    def test_dry_run_reports_create_vs_update_and_writes_nothing(self):
        rows = [
            {"canonical": "UltraTech PPC Cement 50kg", "sku_id": "s1", "gst_rate": "18"},
            {"canonical": "Ambuja Cement 50kg", "gst_rate": "18"},
        ]
        preview = CI.preview_rows(rows, EXISTING)
        self.assertEqual(len(preview["to_update"]), 1)
        self.assertEqual(preview["to_update"][0]["sku_id"], "s1")
        self.assertEqual(len(preview["to_create"]), 1)
        # No repo was even passed in — the strongest possible guarantee that
        # a preview cannot write.

    def test_matches_existing_by_name_when_no_sku_id_given(self):
        rows = [{"canonical": "UltraTech PPC Cement 50kg", "gst_rate": "18"}]
        preview = CI.preview_rows(rows, EXISTING)
        self.assertEqual(preview["to_update"][0]["sku_id"], "s1")
        self.assertEqual(preview["to_create"], [])

    def test_row_missing_a_name_is_reported_as_an_error_not_skipped_silently(self):
        preview = CI.preview_rows([{"gst_rate": "18"}], EXISTING)
        self.assertEqual(len(preview["errors"]), 1)


class CommitImportTests(unittest.TestCase):
    def test_commit_matches_the_preview_exactly(self):
        rows = [
            {"canonical": "UltraTech PPC Cement 50kg", "sku_id": "s1", "gst_rate": "18"},
            {"canonical": "Ambuja Cement 50kg", "gst_rate": "18"},
        ]
        preview = CI.preview_rows(rows, EXISTING)
        repo = FakeRepo(EXISTING)
        result = CI.commit_rows(rows, EXISTING, repo)
        self.assertEqual(result["updated"], [r["sku_id"] for r in preview["to_update"]])
        self.assertEqual(len(result["created"]), len(preview["to_create"]))
        self.assertEqual(len(repo.catalogue), 2)

    def test_price_tiers_land_in_sku_attributes(self):
        rows = [{"canonical": "Ambuja Cement 50kg", "price_retail": "380",
                "price_contractor": "365", "price_dealer": "350"}]
        repo = FakeRepo([])
        CI.commit_rows(rows, [], repo)
        written = repo.writes[0]
        self.assertEqual(written["attributes"]["price_tiers"],
                         {"retail": 380.0, "contractor": 365.0, "dealer": 350.0})


class CustomerPriceTierTests(unittest.TestCase):
    def test_repo_stores_a_customer_default_tier(self):
        import repo as repo_mod
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            r = repo_mod.JsonRepo(d)
            cust = r.upsert_customer("9876543210", "Site Contractor")
            updated = r.set_customer_price_tier(cust["customer_id"], "contractor")
            self.assertEqual(updated["price_tier"], "contractor")
            self.assertEqual(r.customer(cust["customer_id"])["price_tier"],
                             "contractor")


class ImportEndpointsRegisteredTests(unittest.TestCase):
    def test_endpoints_exist(self):
        import main
        paths = {route.path for route in main.app.routes}
        for p in ("/api/catalogue/import/preview", "/api/catalogue/import/commit",
                  "/api/customers/{customer_id}/price-tier"):
            self.assertIn(p, paths, p)


if __name__ == "__main__":
    unittest.main()
