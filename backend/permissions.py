"""B4 — server-side role enforcement.

Roles: owner (everything), manager (everything except deleting records and
changing shop settings), staff (sale entry and lookup only). This is checked
on every request that reaches a sensitive handler in main.py — a UI that
merely hides a button is not enforcement, since the same request can always
be replayed with curl.
"""
from __future__ import annotations

ROLES = ("owner", "manager", "staff")
DEFAULT_ROLE = "owner"

# Capabilities, not endpoints, so a new endpoint just picks the capability it
# needs rather than every role list being re-derived by hand.
_ALLOWED = {
    "owner":   {"sale", "lookup", "write", "delete", "settings", "manage_staff"},
    "manager": {"sale", "lookup", "write"},
    "staff":   {"sale", "lookup"},
}


class PermissionDenied(Exception):
    def __init__(self, role: str, action: str):
        self.role = role
        self.action = action
        super().__init__(f"role '{role}' may not '{action}'")


def can(role: str, action: str) -> bool:
    return action in _ALLOWED.get(role or DEFAULT_ROLE, ())


def require(role: str, action: str) -> None:
    if not can(role, action):
        raise PermissionDenied(role, action)
