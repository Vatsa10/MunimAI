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


if __name__ == "__main__":
    unittest.main()
