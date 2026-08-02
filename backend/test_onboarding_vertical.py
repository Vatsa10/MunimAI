"""Onboarding seeds the hardware vertical pack (spec 3.6), exercised without a
live database: the request-scoped `repo` proxy is bound to a JsonRepo over a
temp dir directly, the same mechanism main.bind_user() uses for a real
request, and main.onboarding() is called as a plain function."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main
import verticals
from repo import JsonRepo


class OnboardingVerticalSeedTests(unittest.TestCase):
    def setUp(self):
        verticals._PACK_CACHE.clear()
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = JsonRepo(Path(self._tmp.name))
        self._repo_token = main._CURRENT.set(self.repo)
        self._user_token = main._CURRENT_USER.set(
            {"user_id": "u_test", "phone": "917000000000"})
        self._patched_onboard = patch.object(
            main.auth, "complete_onboarding", return_value=None)
        self._patched_onboard.start()

    def tearDown(self):
        self._patched_onboard.stop()
        main._CURRENT.reset(self._repo_token)
        main._CURRENT_USER.reset(self._user_token)
        self._tmp.cleanup()

    def test_onboarding_seeds_the_hardware_catalogue(self):
        result = main.onboarding({"shop_name": "Probe Hardware"})
        self.assertEqual(result, {"ok": True})
        self.assertGreaterEqual(len(self.repo.load_catalogue()), 150)

    def test_onboarding_records_the_chosen_vertical(self):
        main.onboarding({"shop_name": "Probe Hardware"})
        cfg = self.repo.load_config()
        self.assertEqual(verticals.tenant_vertical(cfg), ("hardware", "1.0.0"))

    def test_onboarding_never_fails_signup_for_a_malformed_pack(self):
        with patch.object(verticals, "seed_tenant",
                          side_effect=verticals.PackValidationError("boom")):
            result = main.onboarding({"shop_name": "Probe Hardware"})
        self.assertEqual(result, {"ok": True})


if __name__ == "__main__":
    unittest.main()
