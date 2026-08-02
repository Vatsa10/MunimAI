import json
import unittest
from pathlib import Path

import verticals


# GST 2.0 (56th Council, effective 22 September 2025) collapsed the old
# 5/12/18/28 structure to 5/18/40. A catalogue still carrying 28 quietly
# overcharges every bill it touches, because agent.py computes invoice GST
# straight from this field.
GST_2_0_SLABS = {0, 5, 18, 40}


class SeedCatalogueGstTests(unittest.TestCase):
    def test_no_seed_sku_carries_a_pre_reform_gst_rate(self):
        path = Path(__file__).resolve().parent.parent / "data" / "catalogue.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data if isinstance(data, list) else data.get("catalogue", data)
        offenders = [(s.get("sku_id"), s.get("gst_rate")) for s in items
                     if s.get("gst_rate") is not None
                     and s["gst_rate"] not in GST_2_0_SLABS]
        self.assertEqual(offenders, [])


class TenantVerticalTests(unittest.TestCase):
    def test_absent_vertical_reads_as_none(self):
        self.assertEqual(verticals.tenant_vertical({}), (None, None))

    def test_round_trips_through_config(self):
        cfg = verticals.set_tenant_vertical({}, "hardware", "1.0.0")
        self.assertEqual(verticals.tenant_vertical(cfg), ("hardware", "1.0.0"))

    def test_does_not_mutate_the_caller_config(self):
        original = {"shop_name": "Probe Hardware"}
        verticals.set_tenant_vertical(original, "hardware", "1.0.0")
        self.assertNotIn("vertical_id", original)

    def test_preserves_unrelated_config_keys(self):
        cfg = verticals.set_tenant_vertical({"gstin": "27ABCDE1234F1Z5"},
                                            "hardware", "1.0.0")
        self.assertEqual(cfg["gstin"], "27ABCDE1234F1Z5")


if __name__ == "__main__":
    unittest.main()
