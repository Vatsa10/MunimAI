import unittest

import matcher as M


class VerticalPriorStageTests(unittest.TestCase):
    """A shop's own vocabulary must always beat a shipped prior (spec 3.4)."""

    CATALOGUE = [
        {"sku_id": "CEM_A", "canonical": "UltraTech OPC 43 Cement 50kg",
         "family": "cement", "attributes": {"type": "OPC 43", "brand": "UltraTech"},
         "default_unit": "bag", "units": {"bag": 1}, "aliases": ["ultratech opc"]},
        {"sku_id": "CEM_B", "canonical": "Ambuja PPC Cement 50kg",
         "family": "cement", "attributes": {"type": "PPC", "brand": "Ambuja"},
         "default_unit": "bag", "units": {"bag": 1}, "aliases": ["ambuja ppc"]},
    ]
    PRIORS = [{"phrase": "gharelu cement", "sku_ref": "CEM_A", "attributes": {}}]

    def _empty_learning(self):
        return {"aliases_learned": [], "attribute_priors": [], "unit_priors": [],
                "corrections": []}

    def test_vertical_prior_resolves_a_phrase_no_shop_alias_covers(self):
        result = M.match("gharelu cement", self.CATALOGUE, self._empty_learning(),
                          vertical_priors=self.PRIORS)
        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["sku_id"], "CEM_A")
        self.assertEqual(result["stage"], "vertical_prior")

    def test_shop_learned_alias_outranks_a_conflicting_vertical_prior(self):
        learning = self._empty_learning()
        learning["aliases_learned"] = [{"phrase": "gharelu cement", "sku_id": "CEM_B"}]
        result = M.match("gharelu cement", self.CATALOGUE, learning,
                          vertical_priors=self.PRIORS)
        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["sku_id"], "CEM_B")
        self.assertEqual(result["stage"], "alias")

    def test_absent_vertical_priors_do_not_change_existing_behaviour(self):
        result = M.match("ultratech opc", self.CATALOGUE, self._empty_learning())
        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["sku_id"], "CEM_A")


if __name__ == "__main__":
    unittest.main()
