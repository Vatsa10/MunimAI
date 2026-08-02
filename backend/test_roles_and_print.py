"""B4 — server-side role enforcement and thermal/A4 print layouts."""
import unittest
from datetime import date
from unittest.mock import patch

import permissions
import pdfs

LINES = [{"name": "UltraTech PPC Cement 50kg", "qty": 5, "unit": "bag",
         "rate": 380, "amount": 1900}]


class PermissionsTests(unittest.TestCase):
    def test_owner_can_do_everything(self):
        for action in ("sale", "lookup", "write", "delete", "settings",
                      "manage_staff"):
            self.assertTrue(permissions.can("owner", action), action)

    def test_manager_cannot_delete_or_change_settings(self):
        self.assertTrue(permissions.can("manager", "sale"))
        self.assertTrue(permissions.can("manager", "write"))
        self.assertFalse(permissions.can("manager", "delete"))
        self.assertFalse(permissions.can("manager", "settings"))
        self.assertFalse(permissions.can("manager", "manage_staff"))

    def test_staff_is_sale_and_lookup_only(self):
        self.assertTrue(permissions.can("staff", "sale"))
        self.assertTrue(permissions.can("staff", "lookup"))
        self.assertFalse(permissions.can("staff", "write"))
        self.assertFalse(permissions.can("staff", "delete"))
        self.assertFalse(permissions.can("staff", "settings"))

    def test_require_raises_for_a_disallowed_action(self):
        with self.assertRaises(permissions.PermissionDenied):
            permissions.require("staff", "delete")

    def test_unknown_role_gets_no_permissions(self):
        self.assertFalse(permissions.can("intern", "lookup"))


class ServerSideEnforcementTests(unittest.TestCase):
    """The enforcement lives in the request handler, not the UI — replaying
    the same request with a staff session must fail regardless of what the
    client sent."""

    def _client_as(self, role):
        import main
        from fastapi.testclient import TestClient

        class _FakeRepo:
            def customer(self, cid):
                return {"customer_id": cid, "name": "X"}
            def delete_customer(self, cid):
                return True
            def sku(self, sid):
                return {"sku_id": sid}
            def events_for_sku(self, sid):
                return []
            def delete_sku(self, sid):
                return True
            def save_config(self, patch):
                return None
            def load_config(self):
                return {}

        fake_user = {"user_id": "usr_staff", "role": role,
                    "ledger_user_id": "usr_owner1"}

        def _fake_bind_user(user):
            main._CURRENT_USER.set(fake_user)
            main._CURRENT.set(_FakeRepo())

        patcher1 = patch.object(main.auth, "user_for_token",
                                lambda token: fake_user)
        patcher2 = patch.object(main, "bind_user", _fake_bind_user)
        self.addCleanup(patcher1.stop)
        self.addCleanup(patcher2.stop)
        patcher1.start()
        patcher2.start()
        return TestClient(main.app)

    def test_staff_cannot_delete_a_customer(self):
        client = self._client_as("staff")
        resp = client.delete("/api/customers/cust_0001",
                             headers={"Authorization": "Bearer irrelevant"})
        self.assertEqual(resp.status_code, 403)

    def test_manager_cannot_change_settings(self):
        client = self._client_as("manager")
        resp = client.post("/api/config", json={"gst_default": 5},
                           headers={"Authorization": "Bearer irrelevant"})
        self.assertEqual(resp.status_code, 403)

    def test_owner_can_delete_a_customer(self):
        client = self._client_as("owner")
        resp = client.delete("/api/customers/cust_0001",
                             headers={"Authorization": "Bearer irrelevant"})
        self.assertEqual(resp.status_code, 200)


class ThermalPrintPdfTests(unittest.TestCase):
    def test_58mm_renders(self):
        pdf = pdfs.thermal_bill_pdf(
            width_mm=58, shop="Probe Hardware", owner="Ramesh",
            customer={"name": "Walk-in"}, lines=LINES, subtotal=1900, gst=342,
            total=2242, bill_no="B-0001", on=date(2026, 8, 2), payment="cash")
        self.assertTrue(pdf.startswith(b"%PDF"))

    def test_80mm_renders(self):
        pdf = pdfs.thermal_bill_pdf(
            width_mm=80, shop="Probe Hardware", owner="Ramesh",
            customer={"name": "Walk-in"}, lines=LINES, subtotal=1900, gst=342,
            total=2242, bill_no="B-0001", on=date(2026, 8, 2), payment="credit")
        self.assertTrue(pdf.startswith(b"%PDF"))

    def test_rejects_an_unsupported_width(self):
        with self.assertRaises(ValueError):
            pdfs.thermal_bill_pdf(
                width_mm=100, shop="S", owner="O", customer={}, lines=LINES,
                subtotal=1900, gst=342, total=2242, bill_no="B-0001",
                on=date(2026, 8, 2), payment="cash")


class StaffRoutesRegisteredTests(unittest.TestCase):
    def test_endpoints_exist(self):
        import main
        paths = {route.path for route in main.app.routes}
        for p in ("/api/staff", "/api/bill/thermal"):
            self.assertIn(p, paths, p)


if __name__ == "__main__":
    unittest.main()
