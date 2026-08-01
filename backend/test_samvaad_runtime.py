import os
import unittest
from unittest.mock import patch

import samvaad_runtime


class _Response:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class _Client:
    def __init__(self, response, calls):
        self.response = response
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


class SamvaadRuntimeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env = patch.dict(
            os.environ,
            {
                "SAMVAAD_API_KEY": "server-only-key",
                "SAMVAAD_ORG_ID": "org-1",
                "SAMVAAD_WORKSPACE_ID": "workspace-1",
                "SAMVAAD_APP_ID": "app-1",
                "SAMVAAD_AGENT_VERSION": "7",
            },
            clear=False,
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_browser_config_never_exposes_api_key(self):
        config = samvaad_runtime.browser_config()
        self.assertTrue(config["enabled"])
        self.assertEqual(config["version"], 7)
        self.assertEqual(config["proxy_base_url"], "/api/voice/samvaad/")
        self.assertNotIn("api_key", config)
        self.assertNotIn("server-only-key", repr(config))

    def test_app_defaults_to_committed_version_six(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(samvaad_runtime.settings().version, 6)

    def test_sarvam_key_is_the_only_key_a_deployment_must_set(self):
        # SARVAM_API_KEY alone must light up voice: org/workspace/app all have
        # committed defaults, so a bare deployment should still be enabled.
        with patch.dict(os.environ, {"SARVAM_API_KEY": "sk_only"}, clear=True):
            cfg = samvaad_runtime.settings()
            self.assertEqual(cfg.api_key, "sk_only")
            self.assertTrue(cfg.enabled)

    def test_dedicated_samvaad_key_still_wins_when_set(self):
        with patch.dict(os.environ,
                        {"SAMVAAD_API_KEY": "dedicated", "SARVAM_API_KEY": "sk_only"},
                        clear=True):
            self.assertEqual(samvaad_runtime.settings().api_key, "dedicated")

    def test_placeholder_samvaad_key_falls_back_instead_of_failing_upstream(self):
        # A "......" placeholder in .env used to be sent verbatim as X-API-Key,
        # so voice failed at Sarvam with no local signal that the key was junk.
        for placeholder in ("", "   ", "......", "..."):
            with self.subTest(placeholder=placeholder):
                with patch.dict(os.environ,
                                {"SAMVAAD_API_KEY": placeholder,
                                 "SARVAM_API_KEY": "sk_only"}, clear=True):
                    self.assertEqual(samvaad_runtime.settings().api_key, "sk_only")

    def test_placeholder_ids_do_not_override_committed_defaults(self):
        with patch.dict(os.environ,
                        {"SARVAM_API_KEY": "sk_only",
                         "SAMVAAD_ORG_ID": "...",
                         "SAMVAAD_WORKSPACE_ID": "...",
                         "SAMVAAD_APP_ID": "...",
                         "SAMVAAD_AGENT_VERSION": "..."}, clear=True):
            cfg = samvaad_runtime.settings()
            self.assertEqual(cfg.org_id, samvaad_runtime.DEFAULT_ORG_ID)
            self.assertEqual(cfg.workspace_id, samvaad_runtime.DEFAULT_WORKSPACE_ID)
            self.assertEqual(cfg.app_id, samvaad_runtime.DEFAULT_APP_ID)
            self.assertEqual(cfg.version, samvaad_runtime.DEFAULT_AGENT_VERSION)

    def test_no_key_anywhere_disables_voice(self):
        with patch.dict(os.environ, {"SAMVAAD_API_KEY": "......"}, clear=True):
            cfg = samvaad_runtime.browser_config()
            self.assertFalse(cfg["enabled"])
            self.assertIn("SARVAM_API_KEY", cfg["reason"])

    async def test_signed_url_is_limited_to_configured_agent(self):
        with self.assertRaises(PermissionError):
            await samvaad_runtime.get_signed_url(
                "other-org",
                "workspace-1",
                "app-1",
                interaction_type="call",
                version=7,
            )

    async def test_signed_url_uses_server_key_and_pinned_version(self):
        calls = []
        response = _Response(
            payload={
                "url": "wss://signed.example/session",
                "reference_id": "ref-123",
            }
        )
        factory = lambda **_kwargs: _Client(response, calls)
        with patch.object(samvaad_runtime.httpx, "AsyncClient", factory):
            result = await samvaad_runtime.get_signed_url(
                "org-1",
                "workspace-1",
                "app-1",
                interaction_type="call",
                version=7,
            )

        self.assertEqual(result["reference_id"], "ref-123")
        self.assertEqual(len(calls), 1)
        _url, kwargs = calls[0]
        self.assertEqual(kwargs["headers"]["X-API-Key"], "server-only-key")
        self.assertEqual(kwargs["params"]["interaction_type"], "call")
        self.assertEqual(kwargs["params"]["version"], 7)

    async def test_browser_cannot_select_another_pinned_version(self):
        with self.assertRaises(PermissionError):
            await samvaad_runtime.get_signed_url(
                "org-1",
                "workspace-1",
                "app-1",
                interaction_type="call",
                version=8,
            )


if __name__ == "__main__":
    unittest.main()
