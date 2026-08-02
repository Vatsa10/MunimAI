"""SqlRepo.set_customer_price_tier and the /api/customers/{id}/price-tier
route that dispatches to it.

sqlrepo.py used to be frozen for a parallel A/B/C build, so this capability
only existed on JsonRepo and the Postgres route returned 501. Now that the
build has merged, SqlRepo implements it too and the route always dispatches.
No test here touches a live database: SqlRepo is exercised against a fake
connection/cursor, the same shape psycopg would hand back.
"""
import unittest
from contextlib import contextmanager
from unittest.mock import patch


class _FakeCursor:
    def __init__(self, fetchone_result=None, description=None, rows=None):
        self._fetchone_result = fetchone_result
        self.description = description
        self._rows = rows or []

    def fetchone(self):
        return self._fetchone_result

    def fetchall(self):
        return self._rows


class _FakeConn:
    """Records every statement it is asked to run.

    `customer_exists` controls the "SELECT 1 ... customer_id" existence
    check; `select_rows` seeds what the follow-up `customers()` reload sees.
    """

    def __init__(self, customer_exists=True, select_rows=None):
        self.customer_exists = customer_exists
        self.select_rows = select_rows or []
        self.statements = []

    def execute(self, sql, params=None):
        self.statements.append((sql, params))
        upper = sql.strip().upper()
        if upper.startswith("SELECT 1 FROM CUSTOMERS"):
            return _FakeCursor(fetchone_result=(1,) if self.customer_exists else None)
        if upper.startswith("SELECT CUSTOMER_ID"):
            cols = ["customer_id", "phone", "name", "created_at",
                    "updated_at", "price_tier"]
            description = [type("Col", (), {"name": c})() for c in cols]
            return _FakeCursor(description=description, rows=self.select_rows)
        return _FakeCursor()


def _fake_connect_factory(fake_conn):
    @contextmanager
    def _connect():
        yield fake_conn
    return _connect


class SqlRepoPriceTierTests(unittest.TestCase):
    def _repo(self, fake_conn):
        import sqlrepo

        repo = sqlrepo.SqlRepo("usr_1")
        self._patcher = patch.object(sqlrepo.db, "connect",
                                     _fake_connect_factory(fake_conn))
        self._patcher.start()
        self.addCleanup(self._patcher.stop)
        return repo

    def test_sets_tier_and_returns_the_updated_customer(self):
        fake_conn = _FakeConn(
            customer_exists=True,
            select_rows=[("cust_1", "+919876543210", "Ramesh",
                          "2026-01-01T00:00:00", None, "contractor")])
        repo = self._repo(fake_conn)

        result = repo.set_customer_price_tier("cust_1", "contractor")

        self.assertEqual(result["price_tier"], "contractor")
        update_stmts = [s for s, _ in fake_conn.statements
                        if s.strip().upper().startswith("UPDATE CUSTOMERS")]
        self.assertEqual(len(update_stmts), 1)
        # user_id scoping: every statement touching this row must carry it.
        self.assertIn("user_id = %s", update_stmts[0])

    def test_raises_for_an_unknown_customer(self):
        fake_conn = _FakeConn(customer_exists=False)
        repo = self._repo(fake_conn)

        with self.assertRaises(ValueError):
            repo.set_customer_price_tier("cust_missing", "dealer")

    def test_invalidates_the_stale_customers_cache(self):
        fake_conn = _FakeConn(
            customer_exists=True,
            select_rows=[("cust_1", "+919876543210", "Ramesh",
                          "2026-01-01T00:00:00", None, "dealer")])
        repo = self._repo(fake_conn)
        repo._memo["customers"] = ["stale"]

        repo.set_customer_price_tier("cust_1", "dealer")

        # The stale pre-write cache must not survive: what's cached now was
        # reloaded after the UPDATE, not the "stale" sentinel seeded above.
        self.assertNotEqual(repo._memo["customers"], ["stale"])


class RouteDispatchTests(unittest.TestCase):
    """The 501 dead branch is gone: any bound repo with the method is used,
    and a ValueError from the repo becomes 404, not a stub response."""

    def _client_as(self, repo):
        import main
        from fastapi.testclient import TestClient

        fake_user = {"user_id": "usr_owner1", "role": "owner",
                    "ledger_user_id": "usr_owner1"}

        def _fake_bind_user(user):
            main._CURRENT_USER.set(fake_user)
            main._CURRENT.set(repo)

        patcher1 = patch.object(main.auth, "user_for_token",
                                lambda token: fake_user)
        patcher2 = patch.object(main, "bind_user", _fake_bind_user)
        self.addCleanup(patcher1.stop)
        self.addCleanup(patcher2.stop)
        patcher1.start()
        patcher2.start()
        return TestClient(main.app)

    def test_route_no_longer_501s_when_the_repo_implements_it(self):
        class _Repo:
            def set_customer_price_tier(self, customer_id, tier):
                return {"customer_id": customer_id, "price_tier": tier}

        client = self._client_as(_Repo())
        resp = client.post("/api/customers/cust_1/price-tier",
                           json={"tier": "dealer"},
                           headers={"Authorization": "Bearer irrelevant"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["price_tier"], "dealer")

    def test_route_maps_a_missing_customer_to_404_not_a_stub(self):
        class _Repo:
            def set_customer_price_tier(self, customer_id, tier):
                raise ValueError("customer not found")

        client = self._client_as(_Repo())
        resp = client.post("/api/customers/cust_missing/price-tier",
                           json={"tier": "dealer"},
                           headers={"Authorization": "Bearer irrelevant"})
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
