"""Structural tests for the shipped hardware pack, independent of the loader."""
import json
import unittest
from pathlib import Path

import yaml

PACK_DIR = Path(__file__).resolve().parent.parent / "verticals" / "hardware"

GST_RATES = {"cement": (18, "2523"), "tmt": (18, "7214"),
             "structural_steel": (18, "7216"), "tiles": (18, "6907"),
             "plywood": (18, "4412"), "wire": (18, "8544"),
             "pipe_pvc": (18, "3917"), "paint": (18, "3208")}


def _read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8")
            .splitlines() if line.strip()]


class PackFilesExistTests(unittest.TestCase):
    def test_meta_yaml_has_required_keys(self):
        meta = yaml.safe_load((PACK_DIR / "meta.yaml").read_text(encoding="utf-8"))
        self.assertEqual(meta["vertical_id"], "hardware")
        self.assertEqual(meta["pack_version"], "1.0.0")
        self.assertIn("display_name", meta)

    def test_units_yaml_declares_conversion_factors(self):
        units = yaml.safe_load((PACK_DIR / "units.yaml").read_text(encoding="utf-8"))
        self.assertIn("bag", units)
        self.assertIn("tonne", units)
        self.assertIn("bundle", units)
        self.assertIn("rft", units)

    def test_attributes_yaml_declares_real_indian_standards(self):
        attrs = yaml.safe_load((PACK_DIR / "attributes.yaml").read_text(encoding="utf-8"))
        self.assertIn("Fe500", attrs["tmt_grade"])
        self.assertIn("Fe500D", attrs["tmt_grade"])
        self.assertIn("Fe550", attrs["tmt_grade"])
        self.assertIn("OPC 43", attrs["cement_type"])
        self.assertIn("OPC 53", attrs["cement_type"])
        self.assertIn("PPC", attrs["cement_type"])
        self.assertIn("MR", attrs["plywood_grade"])
        self.assertIn("BWR", attrs["plywood_grade"])
        self.assertIn("BWP", attrs["plywood_grade"])

    def test_reports_yaml_lists_dashboards(self):
        reports = yaml.safe_load((PACK_DIR / "reports.yaml").read_text(encoding="utf-8"))
        self.assertIsInstance(reports["dashboards"], list)
        self.assertGreater(len(reports["dashboards"]), 0)


class CatalogueSeedTests(unittest.TestCase):
    def setUp(self):
        self.rows = _read_jsonl(PACK_DIR / "catalogue_seed.jsonl")

    def test_has_at_least_150_skus(self):
        self.assertGreaterEqual(len(self.rows), 150)

    def test_sku_ids_are_unique(self):
        ids = [r["sku_id"] for r in self.rows]
        self.assertEqual(len(ids), len(set(ids)))

    def test_no_row_carries_a_price_field(self):
        for r in self.rows:
            for banned in ("cost_price", "selling_rate", "opening_cost_per_kg",
                           "landed_cost_per_kg", "rate", "price"):
                self.assertNotIn(banned, r, r["sku_id"])

    def test_gst_and_hsn_match_gst_map_by_family(self):
        for r in self.rows:
            family = r["family"]
            self.assertIn(family, GST_RATES, r["sku_id"])
            rate, hsn = GST_RATES[family]
            self.assertEqual(r["gst_rate"], rate, r["sku_id"])
            self.assertEqual(r["hsn"], hsn, r["sku_id"])

    def test_every_row_has_required_fields(self):
        for r in self.rows:
            for field in ("sku_id", "canonical", "family", "brand", "attributes",
                          "default_unit", "units", "gst_rate", "hsn", "aliases"):
                self.assertIn(field, r, f"{r.get('sku_id')} missing {field}")
            self.assertIn(r["default_unit"], r["units"], r["sku_id"])
            self.assertGreater(len(r["aliases"]), 0, r["sku_id"])

    def test_tmt_rows_use_real_grades_and_diameters(self):
        tmt = [r for r in self.rows if r["family"] == "tmt"]
        self.assertGreater(len(tmt), 0)
        for r in tmt:
            self.assertIn(r["attributes"]["grade"], ("Fe500", "Fe500D", "Fe550"), r["sku_id"])
            self.assertIn(r["attributes"]["diameter_mm"], (8, 10, 12, 16, 20, 25), r["sku_id"])

    def test_cement_rows_use_real_types(self):
        cement = [r for r in self.rows if r["family"] == "cement"]
        self.assertGreater(len(cement), 0)
        for r in cement:
            self.assertIn(r["attributes"]["type"], ("OPC 43", "OPC 53", "PPC", "PSC"), r["sku_id"])

    def test_brands_are_from_the_real_indian_roster(self):
        allowed = {"UltraTech", "Ambuja", "ACC", "Shree", "Dalmia",
                  # Tata Tiscon and JSW Neosteel are TMT rebar brand lines and
                  # must not appear on structural sections; Jindal and JSW roll
                  # angles and channels to IS 2062 / IS 808.
                  "Tata Tiscon", "JSW Neosteel", "Jindal", "JSW",
                  "SAIL", "Vizag",
                  "Havells", "Polycab", "Finolex", "RR Kabel",
                  "Century", "Greenply", "Kajaria", "Somany",
                  "Supreme", "Astral", "Asian Paints", "Berger",
                  "Nerolac", "Dulux", "JK", "JK Lakshmi"}
        for r in self.rows:
            self.assertIn(r["brand"], allowed, r["sku_id"])

    def test_aliases_include_a_hindi_or_romanized_spoken_form(self):
        romanized_markers = ("saria", "sariya", "bori", "bora", "cement",
                             "tar", "seet", "pata", "mota", "patla", "rang",
                             "pipe", "tile", "wire", "ply")
        rows_with_marker = [r for r in self.rows if any(
            any(marker in a.lower() for marker in romanized_markers)
            for a in r["aliases"])]
        self.assertGreater(len(rows_with_marker), len(self.rows) * 0.5)


class AliasPriorsTests(unittest.TestCase):
    def test_every_alias_prior_resolves_to_a_real_sku(self):
        catalogue_ids = {r["sku_id"] for r in _read_jsonl(PACK_DIR / "catalogue_seed.jsonl")}
        priors = _read_jsonl(PACK_DIR / "alias_priors.jsonl")
        self.assertGreater(len(priors), 0)
        for p in priors:
            self.assertIn(p["sku_ref"], catalogue_ids, p["phrase"])

    def test_no_duplicate_phrases(self):
        priors = _read_jsonl(PACK_DIR / "alias_priors.jsonl")
        phrases = [p["phrase"] for p in priors]
        self.assertEqual(len(phrases), len(set(phrases)))


if __name__ == "__main__":
    unittest.main()
