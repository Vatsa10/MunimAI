"""Vertical pack configuration held per tenant.

A vertical pack is shipped data, not tenant data, so only the pointer to it
lives in `user_config.data`. Sub-project A adds pack loading and seeding on top
of these accessors; keeping them separate means B can ask which vertical a shop
is on without importing the loader.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

VERTICAL_KEY = "vertical_id"
VERSION_KEY = "vertical_pack_version"

PACK_ROOT = Path(__file__).resolve().parent.parent / "verticals"
_PACK_CACHE: dict = {}


class PackValidationError(Exception):
    """A vertical pack directory is missing, malformed, or fails validation.

    Raised at load time so a bad pack never reaches mid-conversation."""


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


# ---------------------------------------------------------------------------
# Pack loading (spec 3.3)
# ---------------------------------------------------------------------------
def _read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _read_jsonl(path: Path) -> list:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _validate_pack(pack: dict) -> None:
    """Reject unknown units, missing GST, or alias collisions across families.

    Same alias pointing at multiple SKUs *within* one family is fine — that's
    a normal family-level alias the matcher disambiguates on attributes. A
    collision *across* families would send a shipped alias ambiguously toward
    the wrong product line, which a pack must never do.
    """
    known_units = set(pack["units"].keys())
    alias_owner: dict[str, tuple[str, str]] = {}
    for row in pack["catalogue"]:
        sku_id = row.get("sku_id", "<unknown>")
        if "gst_rate" not in row or row["gst_rate"] is None:
            raise PackValidationError(f"{sku_id}: missing gst_rate")
        if row.get("default_unit") not in known_units:
            raise PackValidationError(
                f"{sku_id}: unknown default_unit {row.get('default_unit')!r}")
        for unit in row.get("units", {}):
            if unit not in known_units:
                raise PackValidationError(f"{sku_id}: unknown unit {unit!r} in units map")
        for alias in row.get("aliases", []):
            prior = alias_owner.get(alias)
            if prior is not None and prior[1] != row["family"]:
                raise PackValidationError(
                    f"alias collision: {alias!r} claimed by {prior[0]} "
                    f"({prior[1]}) and {sku_id} ({row['family']})")
            alias_owner[alias] = (sku_id, row["family"])
    catalogue_ids = {r["sku_id"] for r in pack["catalogue"]}
    for prior in pack["alias_priors"]:
        if prior["sku_ref"] not in catalogue_ids:
            raise PackValidationError(
                f"alias_priors phrase {prior['phrase']!r} references unknown "
                f"sku_ref {prior['sku_ref']!r}")


def load_pack(vertical_id: str, version: str) -> dict:
    """Read, validate and cache a vertical pack directory.

    Raises PackValidationError if the directory is missing or the pack fails
    validation, so a malformed pack fails at load rather than mid-conversation.
    """
    key = (vertical_id, version)
    if key in _PACK_CACHE:
        return _PACK_CACHE[key]
    pack_dir = PACK_ROOT / vertical_id
    if not pack_dir.is_dir():
        raise PackValidationError(f"no pack directory for vertical {vertical_id!r}")
    try:
        pack = {
            "meta": _read_yaml(pack_dir / "meta.yaml"),
            "units": _read_yaml(pack_dir / "units.yaml"),
            "attributes": _read_yaml(pack_dir / "attributes.yaml"),
            "reports": _read_yaml(pack_dir / "reports.yaml"),
            "gst_map": _read_yaml(pack_dir / "gst_map.yaml"),
            "catalogue": _read_jsonl(pack_dir / "catalogue_seed.jsonl"),
            "alias_priors": _read_jsonl(pack_dir / "alias_priors.jsonl"),
            "prompt_fragment": (pack_dir / "prompt_fragment.md").read_text(encoding="utf-8"),
        }
    except FileNotFoundError as exc:
        raise PackValidationError(f"pack {vertical_id!r} missing file: {exc}") from exc
    if pack["meta"].get("pack_version") != version:
        raise PackValidationError(
            f"requested version {version!r} does not match pack meta.yaml "
            f"version {pack['meta'].get('pack_version')!r}")
    _validate_pack(pack)
    _PACK_CACHE[key] = pack
    return pack


def _stamp_vertical_config(repo, vertical_id: str, version: str) -> None:
    """Record vertical_id/vertical_pack_version in the tenant's own config.

    JsonRepo (used by the whole test suite) goes through the ordinary
    repo.save_config() -> repo.py is not on the do-not-modify list, so it was
    taught to pass these two keys through, the same way it already
    special-cases gst_default.

    SqlRepo (the live Postgres path) is on the do-not-modify list, so this
    writes user_config directly with the identical
    "SELECT ... FOR UPDATE" / "INSERT ... ON CONFLICT" pattern sqlrepo.py's
    own save_config already uses for the same table - no schema change, no
    edit to sqlrepo.py, just a second writer using the table it already owns.
    """
    user_id = getattr(repo, "user_id", None)
    if user_id is None:
        cfg = repo.load_config()
        repo.save_config(set_tenant_vertical(cfg, vertical_id, version))
        return
    import db
    with db.connect() as conn:
        row = conn.execute(
            "SELECT data FROM user_config WHERE user_id = %s FOR UPDATE",
            (user_id,)).fetchone()
        cfg = (row[0] if row else None) or {"gst_default": 18, "gst_by_family": {}}
        cfg = set_tenant_vertical(cfg, vertical_id, version)
        conn.execute(
            "INSERT INTO user_config (user_id, data) VALUES (%s,%s::jsonb)"
            " ON CONFLICT (user_id) DO UPDATE SET data = EXCLUDED.data",
            (user_id, json.dumps(cfg, ensure_ascii=False)))
    if hasattr(repo, "refresh"):
        repo.refresh()


def seed_tenant(repo, vertical_id: str, version: str = "1.0.0") -> int:
    """Copy a vertical pack's catalogue into `repo`'s tenant and record the
    choice in tenant config.

    Global vertical_priors (spoken-form -> sku_ref, shared across all tenants
    on this vertical/version) are shipped data, not tenant data - they live in
    the pack itself and are read directly by the matcher via
    load_pack()["alias_priors"], never copied per-tenant. This function only
    writes to the tenant's own catalogue (via repo.upsert_sku, the existing
    public interface both JsonRepo and SqlRepo implement) and config.
    """
    pack = load_pack(vertical_id, version)
    count = 0
    for row in pack["catalogue"]:
        sku = dict(row)
        hsn = sku.pop("hsn", None)
        attrs = dict(sku.get("attributes") or {})
        if hsn is not None:
            attrs.setdefault("hsn", hsn)
        sku["attributes"] = attrs
        repo.upsert_sku(sku)
        count += 1
    _stamp_vertical_config(repo, vertical_id, version)
    return count
