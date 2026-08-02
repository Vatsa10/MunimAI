"""Spec 3.7 acceptance test: a fresh signup can voice-sell a seeded SKU."""
import tempfile
import unittest
from pathlib import Path

import matcher as M
import repo as repo_mod
import verticals


PHRASES = [
    "ultratech cement", "bori cement", "opc 53 cement", "ppc cement",
    "sariya", "12mm sariya", "solah mm rod", "tata tiscon",
    "havells wire", "2.5 sqmm wire", "polycab cable",
    "century plywood", "mr plywood", "kajaria tile",
    "supreme pipe", "astral pipe", "1 inch pipe",
    "asian paints", "berger paint", "structural angle",
]

# Brand-led phrasing ("ultratech cement do bori") is the single most natural
# way an owner names a product. A previous version of catalogue_seed.jsonl
# put `brand` only at the SKU's top level, not inside `attributes`, so
# matcher.resolve_variant (which compares spoken attrs against
# sku["attributes"]) could never match a spoken brand and returned
# not_stocked for every brand-led phrase. That was a silent, systemic
# failure the old >=16/20 threshold let slip through. This list exists
# specifically to catch that class of regression again.
BRAND_LED_PHRASES = [
    "ultratech cement", "tata tiscon", "ultratech ppc", "tata tiscon 12mm",
    "havells wire", "century plywood", "supreme pipe",
]


class TwentyPhraseResolutionTests(unittest.TestCase):
    def setUp(self):
        verticals._PACK_CACHE.clear()
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = repo_mod.JsonRepo(Path(self._tmp.name))
        verticals.seed_tenant(self.repo, "hardware", "1.0.0")
        self.catalogue = self.repo.load_catalogue()
        self.pack = verticals.load_pack("hardware", "1.0.0")

    def tearDown(self):
        self._tmp.cleanup()

    def test_representative_phrases_resolve_without_adding_a_product(self):
        learning = {"aliases_learned": [], "attribute_priors": [],
                    "unit_priors": [], "corrections": []}
        resolved = 0
        unresolved = []
        for phrase in PHRASES:
            result = M.match(phrase, self.catalogue, learning,
                             vertical_priors=self.pack["alias_priors"])
            if result["status"] in ("matched", "disambiguate"):
                resolved += 1
            else:
                unresolved.append((phrase, result["status"]))
        self.assertGreaterEqual(resolved, 16, f"unresolved: {unresolved}")

    def test_brand_led_phrases_never_come_back_not_stocked(self):
        """Regression guard: brand alone must be a real, matchable attribute
        (spec: attributes.brand), not just cosmetic top-level metadata."""
        learning = {"aliases_learned": [], "attribute_priors": [],
                    "unit_priors": [], "corrections": []}
        failures = []
        for phrase in BRAND_LED_PHRASES:
            result = M.match(phrase, self.catalogue, learning,
                             vertical_priors=self.pack["alias_priors"])
            if result["status"] not in ("matched", "disambiguate"):
                failures.append((phrase, result["status"]))
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
