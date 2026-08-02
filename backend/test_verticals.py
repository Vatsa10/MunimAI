import unittest

import verticals


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
