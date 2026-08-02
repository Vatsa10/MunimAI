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


class LoadPackTests(unittest.TestCase):
    def setUp(self):
        verticals._PACK_CACHE.clear()

    def test_loads_the_hardware_pack(self):
        pack = verticals.load_pack("hardware", "1.0.0")
        self.assertEqual(pack["meta"]["vertical_id"], "hardware")
        self.assertGreaterEqual(len(pack["catalogue"]), 150)
        self.assertGreater(len(pack["alias_priors"]), 0)

    def test_unknown_vertical_raises(self):
        with self.assertRaises(verticals.PackValidationError):
            verticals.load_pack("nonexistent", "1.0.0")

    def test_second_load_is_cached(self):
        first = verticals.load_pack("hardware", "1.0.0")
        second = verticals.load_pack("hardware", "1.0.0")
        self.assertIs(first, second)

    def test_rejects_pack_with_unknown_unit(self):
        import copy
        pack = copy.deepcopy(verticals.load_pack("hardware", "1.0.0"))
        pack["catalogue"][0]["default_unit"] = "furlong"
        with self.assertRaises(verticals.PackValidationError):
            verticals._validate_pack(pack)

    def test_rejects_pack_missing_gst(self):
        import copy
        pack = copy.deepcopy(verticals.load_pack("hardware", "1.0.0"))
        del pack["catalogue"][0]["gst_rate"]
        with self.assertRaises(verticals.PackValidationError):
            verticals._validate_pack(pack)

    def test_rejects_alias_collision_across_families(self):
        import copy
        pack = copy.deepcopy(verticals.load_pack("hardware", "1.0.0"))
        cement = next(r for r in pack["catalogue"] if r["family"] == "cement")
        tmt = next(r for r in pack["catalogue"] if r["family"] == "tmt")
        cement["aliases"] = list(cement["aliases"]) + ["__collision_probe__"]
        tmt["aliases"] = list(tmt["aliases"]) + ["__collision_probe__"]
        with self.assertRaises(verticals.PackValidationError):
            verticals._validate_pack(pack)


class SeedTenantTests(unittest.TestCase):
    def setUp(self):
        import sys
        import tempfile

        verticals._PACK_CACHE.clear()
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import repo as repo_mod
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = repo_mod.JsonRepo(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_seeds_every_catalogue_row_as_a_sku(self):
        pack = verticals.load_pack("hardware", "1.0.0")
        count = verticals.seed_tenant(self.repo, "hardware", "1.0.0")
        self.assertEqual(count, len(pack["catalogue"]))
        self.assertGreaterEqual(len(self.repo.load_catalogue()), 150)

    def test_seeded_skus_carry_no_price_fields(self):
        verticals.seed_tenant(self.repo, "hardware", "1.0.0")
        for sku in self.repo.load_catalogue():
            self.assertNotIn("cost_price", sku)
            self.assertNotIn("selling_rate", sku)

    def test_stamps_tenant_vertical_config(self):
        verticals.seed_tenant(self.repo, "hardware", "1.0.0")
        cfg = self.repo.load_config()
        self.assertEqual(verticals.tenant_vertical(cfg), ("hardware", "1.0.0"))

    def test_seeding_twice_does_not_duplicate_skus(self):
        verticals.seed_tenant(self.repo, "hardware", "1.0.0")
        before = len(self.repo.load_catalogue())
        verticals.seed_tenant(self.repo, "hardware", "1.0.0")
        after = len(self.repo.load_catalogue())
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
