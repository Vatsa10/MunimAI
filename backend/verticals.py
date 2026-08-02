"""Vertical pack configuration held per tenant.

A vertical pack is shipped data, not tenant data, so only the pointer to it
lives in `user_config.data`. Sub-project A adds pack loading and seeding on top
of these accessors; keeping them separate means B can ask which vertical a shop
is on without importing the loader.
"""
from __future__ import annotations

VERTICAL_KEY = "vertical_id"
VERSION_KEY = "vertical_pack_version"


def tenant_vertical(config: dict) -> tuple[str | None, str | None]:
    """Return (vertical_id, pack_version) for a tenant, or (None, None)."""
    if not config:
        return (None, None)
    return (config.get(VERTICAL_KEY) or None, config.get(VERSION_KEY) or None)


def set_tenant_vertical(config: dict, vertical_id: str,
                        pack_version: str) -> dict:
    """Return a copy of `config` pointing at a vertical pack.

    Copies rather than mutates: callers pass the live config dict straight from
    the repo, and an in-place edit would half-apply if the write that follows
    fails.
    """
    updated = dict(config or {})
    updated[VERTICAL_KEY] = vertical_id
    updated[VERSION_KEY] = pack_version
    return updated
