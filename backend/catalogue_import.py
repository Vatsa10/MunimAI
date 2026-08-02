"""B3 — bulk catalogue import from Excel/CSV, with a dry-run preview.

A destructive bulk import without a preview is how shops lose their item
master: one bad column mapping and every SKU's cost price is silently wrong.
So this is always two calls — `preview_rows` (no writes, ever) then
`commit_rows` — and the caller is expected to show the preview to the owner
before calling commit.

Expected columns (case-insensitive, extra columns ignored):
  sku_id (optional — omit to always create), name/canonical (required),
  unit, gst_rate, cost_price, selling_rate, family, brand, hsn,
  price_retail, price_contractor, price_dealer.
"""
from __future__ import annotations

import csv
import io

_COLUMN_ALIASES = {
    "sku_id": "sku_id", "id": "sku_id",
    "name": "canonical", "canonical": "canonical", "product": "canonical",
    "unit": "default_unit", "default_unit": "default_unit",
    "gst_rate": "gst_rate", "gst": "gst_rate",
    "cost_price": "opening_cost_per_kg", "cost": "opening_cost_per_kg",
    "family": "family", "brand": "brand", "hsn": "hsn", "hsn_code": "hsn",
    "price_retail": "price_retail", "retail": "price_retail",
    "price_contractor": "price_contractor", "contractor": "price_contractor",
    "price_dealer": "price_dealer", "dealer": "price_dealer",
    "selling_rate": "selling_rate",
}

_PRICE_TIER_FIELDS = ("price_retail", "price_contractor", "price_dealer")


def _num(v):
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _normalize_row(raw: dict) -> dict:
    out = {}
    for key, value in raw.items():
        if key is None:
            continue
        norm_key = _COLUMN_ALIASES.get(str(key).strip().lower())
        if not norm_key:
            continue
        out[norm_key] = value.strip() if isinstance(value, str) else value
    return out


def parse_rows(content: bytes, filename: str) -> list:
    """Excel (.xlsx) or CSV -> a list of normalized dict rows."""
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm")):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        try:
            header = [str(h).strip() if h is not None else "" for h in next(rows_iter)]
        except StopIteration:
            return []
        out = []
        for row in rows_iter:
            if row is None or all(c is None for c in row):
                continue
            raw = dict(zip(header, row))
            out.append(_normalize_row(raw))
        return out
    # CSV / anything else — decode leniently, a shop's export is rarely pure UTF-8.
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    return [_normalize_row(r) for r in reader if any((v or "").strip() for v in r.values())]


def _row_to_sku(row: dict, sku_id: str) -> dict:
    price_tiers = {tier.split("_")[1]: _num(row[tier])
                   for tier in _PRICE_TIER_FIELDS
                   if row.get(tier) not in (None, "")}
    attributes = {}
    if row.get("hsn"):
        attributes["hsn"] = str(row["hsn"]).strip()
    if price_tiers:
        attributes["price_tiers"] = price_tiers
    sku = {
        "sku_id": sku_id,
        "canonical": row.get("canonical") or sku_id,
        "family": row.get("family"),
        "default_unit": row.get("default_unit") or "unit",
        "gst_rate": _num(row.get("gst_rate")),
        "opening_cost_per_kg": _num(row.get("opening_cost_per_kg")),
        "attributes": attributes,
    }
    if row.get("brand"):
        sku.setdefault("attributes", {})["brand"] = row["brand"]
    return sku


def _match_existing(row: dict, existing_by_id: dict, existing_by_name: dict):
    sku_id = (row.get("sku_id") or "").strip()
    if sku_id and sku_id in existing_by_id:
        return existing_by_id[sku_id]
    name = (row.get("canonical") or "").strip().casefold()
    if name and name in existing_by_name:
        return existing_by_name[name]
    return None


def _slugify_sku_id(name: str, taken: set) -> str:
    base = "".join(ch if ch.isalnum() else "_" for ch in (name or "item").lower()).strip("_")
    base = base or "item"
    candidate = base
    n = 1
    while candidate in taken:
        n += 1
        candidate = f"{base}_{n}"
    taken.add(candidate)
    return candidate


def preview_rows(rows: list, existing_catalogue: list) -> dict:
    """No writes. Returns what commit_rows WOULD do."""
    existing_by_id = {s["sku_id"]: s for s in existing_catalogue}
    existing_by_name = {s.get("canonical", "").casefold(): s for s in existing_catalogue}
    taken_ids = set(existing_by_id)
    to_create, to_update, errors = [], [], []
    for i, row in enumerate(rows):
        if not (row.get("canonical") or row.get("sku_id")):
            errors.append({"row": i + 1, "error": "missing product name/sku_id"})
            continue
        match = _match_existing(row, existing_by_id, existing_by_name)
        if match:
            sku = _row_to_sku(row, match["sku_id"])
            to_update.append({"sku_id": match["sku_id"], "canonical": sku["canonical"]})
        else:
            sku_id = (row.get("sku_id") or "").strip() or _slugify_sku_id(
                row.get("canonical"), taken_ids)
            taken_ids.add(sku_id)
            to_create.append({"sku_id": sku_id, "canonical": row.get("canonical") or sku_id})
    return {"to_create": to_create, "to_update": to_update, "errors": errors,
            "total_rows": len(rows)}


def commit_rows(rows: list, existing_catalogue: list, repo) -> dict:
    """Writes via repo.upsert_sku. Call only after the caller has shown the
    preview to the owner — this performs no matching logic of its own beyond
    what preview_rows already computed, so the two never disagree."""
    existing_by_id = {s["sku_id"]: s for s in existing_catalogue}
    existing_by_name = {s.get("canonical", "").casefold(): s for s in existing_catalogue}
    taken_ids = set(existing_by_id)
    created, updated, errors = [], [], []
    for i, row in enumerate(rows):
        if not (row.get("canonical") or row.get("sku_id")):
            errors.append({"row": i + 1, "error": "missing product name/sku_id"})
            continue
        match = _match_existing(row, existing_by_id, existing_by_name)
        if match:
            sku_id = match["sku_id"]
            sku = _row_to_sku(row, sku_id)
            repo.upsert_sku(sku)
            updated.append(sku_id)
        else:
            sku_id = (row.get("sku_id") or "").strip() or _slugify_sku_id(
                row.get("canonical"), taken_ids)
            taken_ids.add(sku_id)
            sku = _row_to_sku(row, sku_id)
            repo.upsert_sku(sku)
            created.append(sku_id)
    return {"created": created, "updated": updated, "errors": errors}
