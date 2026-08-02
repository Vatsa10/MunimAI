"""B5 — HSN/SAC codes and the e-way bill threshold.

HSN lives per-SKU in the existing `skus.attributes` JSONB (no new column).
When a SKU has none set directly, a loaded vertical pack's `gst_map.yaml`
supplies a category default — this is the one deliberate coupling between
sub-project A (which ships the pack) and B (which consumes it). With no
vertical pack loaded, HSN degrades to blank rather than a guess: a wrong HSN
on a real GST invoice is worse than an empty box a human fills in.

E-way bill scope is intentionally narrow: surface the >Rs 50,000 requirement
and let the bill number be captured on the invoice. No government portal
integration — that's out of scope, same concession as IRP e-invoicing.
"""
from __future__ import annotations

from pathlib import Path

VERTICALS_DIR = Path(__file__).resolve().parent.parent / "verticals"
EWAY_BILL_THRESHOLD = 50_000

_gst_map_cache: dict = {}


def load_gst_map(vertical_id: str):
    """Returns the parsed gst_map.yaml for a vertical, or None if the vertical
    isn't set or the pack doesn't ship one. Cached per process like the other
    vertical pack loaders."""
    if not vertical_id:
        return None
    if vertical_id in _gst_map_cache:
        return _gst_map_cache[vertical_id]
    path = VERTICALS_DIR / vertical_id / "gst_map.yaml"
    data = None
    if path.exists():
        import yaml
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    _gst_map_cache[vertical_id] = data
    return data


def hsn_for_sku(sku: dict, gst_map) -> str:
    """The SKU's own HSN wins if set; otherwise the vertical pack's
    category default; otherwise blank."""
    attrs = (sku or {}).get("attributes") or {}
    if attrs.get("hsn"):
        return str(attrs["hsn"])
    if not gst_map:
        return ""
    family = (sku or {}).get("family")
    category = (gst_map.get("categories") or {}).get(family) or {}
    return str(category.get("hsn") or "")


def eway_bill_required(invoice_total: float) -> bool:
    return float(invoice_total or 0) > EWAY_BILL_THRESHOLD
