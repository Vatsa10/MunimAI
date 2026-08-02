# Sub-project A — Vertical Pack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the `verticals/hardware/` pack plus the loader, matcher stage, prompt
composition and onboarding wiring so a fresh signup can complete a voice sale of
a seeded SKU with zero catalogue setup, per spec section 3.

**Architecture:** The pack is plain data files under `verticals/hardware/`.
`backend/verticals.py` (already has `tenant_vertical`/`set_tenant_vertical`)
gains `load_pack()` (validate + cache) and `seed_tenant()` (write pack data into
a tenant's own repo via the existing `Repo` interface — `upsert_sku`,
`save_config` — never by touching `sqlrepo.py`/`db.py` internals). The global
`vertical_priors` table (already created by the foundation in `db.py`) is
written and read directly through `db.connect()` from `verticals.py`, since it
is tenant-agnostic shipped data, not part of any tenant's JSON document.
`matcher.match()` gains one new stage between the existing alias stage and the
attribute/fuzzy stages. `samvaad_config.py` appends `prompt_fragment.md` to the
base prompt without touching the tool list.

**Tech Stack:** Python 3.12, PyYAML (check availability first), existing
`backend/repo.py` (`JsonRepo`) used by the test suite, `backend/db.py` for the
global priors table.

## Global Constraints

- Run tests as: `cd backend && DATABASE_URL= PYTHONIOENCODING=utf-8 <repo-root>/venv/Scripts/python.exe -m unittest discover -s . -p 'test_*.py'`. DATABASE_URL must be empty. Baseline is 223 tests passing; never regress it.
- Use the venv python, never bare `python`.
- Do NOT modify `backend/ledger.py` `_TYPE_ORDER`/`_stock_detail`, `backend/sqlrepo.py`, or existing statements in `backend/db.py`. New DDL, if any, is appended and idempotent only (none is expected — `vertical_priors` already exists).
- Only edit `frontend/index.html` between `<!-- @section:onboarding -->` and `<!-- @endsection:onboarding -->`.
- Build on `backend/verticals.py`'s existing `tenant_vertical`/`set_tenant_vertical`.
- No test may require a live database — all tests use `JsonRepo` over a temp dir.
- `catalogue_seed.jsonl` rows carry no `cost_price`/`selling_rate`/`opening_cost_per_kg`/`landed_cost_per_kg`.
- Every `gst_rate`/`hsn` in the seed comes from `verticals/hardware/gst_map.yaml` — never invented.
- Commit messages: no Claude attribution.

---

### Task 1: Pack scaffold — meta.yaml, units.yaml, attributes.yaml, reports.yaml

**Files:**
- Create: `verticals/hardware/meta.yaml`, `verticals/hardware/units.yaml`, `verticals/hardware/attributes.yaml`, `verticals/hardware/reports.yaml`
- Test: `backend/test_verticals_pack.py` (create)

**Interfaces:**
- Produces: on-disk YAML files consumed by `verticals.load_pack()` in Task 3.

- [ ] **Step 1: Write the failing test**

Create `backend/test_verticals_pack.py`:

```python
"""Structural tests for the shipped hardware pack, independent of the loader."""
import unittest
from pathlib import Path

import yaml

PACK_DIR = Path(__file__).resolve().parent.parent / "verticals" / "hardware"


class PackFilesExistTests(unittest.TestCase):
    def test_meta_yaml_has_required_keys(self):
        meta = yaml.safe_load((PACK_DIR / "meta.yaml").read_text(encoding="utf-8"))
        self.assertEqual(meta["vertical_id"], "hardware")
        self.assertEqual(meta["pack_version"], "1.0.0")
        self.assertIn("display_name", meta)

    def test_units_yaml_declares_conversion_factors(self):
        units = yaml.safe_load((PACK_DIR / "units.yaml").read_text(encoding="utf-8"))
        self.assertIn("bag", units)
        self.assertIn("tonne", units)
        self.assertIn("bundle", units)
        self.assertIn("rft", units)

    def test_attributes_yaml_declares_real_indian_standards(self):
        attrs = yaml.safe_load((PACK_DIR / "attributes.yaml").read_text(encoding="utf-8"))
        self.assertIn("Fe500", attrs["tmt_grade"])
        self.assertIn("Fe500D", attrs["tmt_grade"])
        self.assertIn("Fe550", attrs["tmt_grade"])
        self.assertIn("OPC 43", attrs["cement_type"])
        self.assertIn("OPC 53", attrs["cement_type"])
        self.assertIn("PPC", attrs["cement_type"])
        self.assertIn("MR", attrs["plywood_grade"])
        self.assertIn("BWR", attrs["plywood_grade"])
        self.assertIn("BWP", attrs["plywood_grade"])

    def test_reports_yaml_lists_dashboards(self):
        reports = yaml.safe_load((PACK_DIR / "reports.yaml").read_text(encoding="utf-8"))
        self.assertIsInstance(reports["dashboards"], list)
        self.assertGreater(len(reports["dashboards"]), 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && DATABASE_URL= PYTHONIOENCODING=utf-8 ../venv/Scripts/python.exe -m unittest test_verticals_pack -v`
Expected: FAIL — files do not exist (or `yaml` import fails; if `import yaml` fails, install is not required — fall back to writing `verticals.py`'s own tiny YAML-subset parser in Task 3 and change this test to use that parser instead of PyYAML. Check `venv` for `yaml` first with `../venv/Scripts/python.exe -c "import yaml"`).

- [ ] **Step 3: Write the pack files**

`verticals/hardware/meta.yaml`:
```yaml
vertical_id: hardware
pack_version: "1.0.0"
display_name: "Hardware & Building Materials"
```

`verticals/hardware/units.yaml` (base unit per family is kg or piece = 1; factors express how many base units one of this unit holds):
```yaml
# Conversion factors are family-specific and live per-SKU in catalogue_seed.jsonl
# (each SKU's own "units" map). This file lists the vocabulary of units the
# pack recognizes at all, so the loader can reject an unknown unit.
bag: {base: kg, note: "cement/PPC/PSC bag, commonly 50kg"}
tonne: {base: kg, note: "1000kg, used for TMT/structural steel"}
kg: {base: kg, note: "base unit for steel and cement"}
piece: {base: piece, note: "single TMT rod, tile box unit fallback"}
bundle: {base: piece, note: "wire coil bundle, plywood bundle"}
rft: {base: rft, note: "running feet, structural steel/angle"}
sqft: {base: sqft, note: "tiles"}
box: {base: box, note: "tile box, typically covers ~1-1.5 sqm"}
litre: {base: litre, note: "paint"}
metre: {base: metre, note: "wire by the metre"}
```

`verticals/hardware/attributes.yaml`:
```yaml
tmt_grade: ["Fe500", "Fe500D", "Fe550"]
tmt_diameter_mm: [8, 10, 12, 16, 20, 25]
cement_type: ["OPC 43", "OPC 53", "PPC", "PSC"]
plywood_grade: ["MR", "BWR", "BWP"]
wire_size_sqmm: [0.75, 1, 1.5, 2.5, 4, 6]
pipe_class: ["Class 2", "Class 3", "Class 4"]
brands:
  cement: ["UltraTech", "Ambuja", "ACC", "Shree", "Dalmia"]
  tmt: ["Tata Tiscon", "JSW Neosteel", "SAIL", "Vizag"]
  wire: ["Havells", "Polycab", "Finolex", "RR Kabel"]
  plywood: ["Century", "Greenply"]
  tiles: ["Kajaria", "Somany"]
  pipe_pvc: ["Supreme", "Astral", "Finolex"]
```

`verticals/hardware/reports.yaml`:
```yaml
dashboards:
  - id: stock_by_family
    title: "Stock by category (cement, TMT, wire, plywood, tiles, pipe, paint)"
  - id: gst_summary
    title: "GST collected by HSN code"
  - id: fast_movers
    title: "Top-moving SKUs this month"
  - id: dead_stock
    title: "SKUs with no sale in 60 days"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && DATABASE_URL= PYTHONIOENCODING=utf-8 ../venv/Scripts/python.exe -m unittest test_verticals_pack -v`
Expected: PASS, 4 tests.

- [ ] **Step 5: Commit**

```bash
git add verticals/hardware/meta.yaml verticals/hardware/units.yaml verticals/hardware/attributes.yaml verticals/hardware/reports.yaml backend/test_verticals_pack.py
git commit -m "feat(hardware-pack): add meta, units, attributes and reports scaffolding"
```

---

### Task 2: Catalogue seed and alias priors (data authoring)

**Files:**
- Create: `verticals/hardware/catalogue_seed.jsonl`, `verticals/hardware/alias_priors.jsonl`
- Test: extend `backend/test_verticals_pack.py`

**Interfaces:**
- Produces: one JSON object per line in `catalogue_seed.jsonl` with keys
  `sku_id, canonical, family, brand, attributes, default_unit, units, gst_rate,
  hsn, aliases` (no price fields). `alias_priors.jsonl`: `{"phrase": str,
  "sku_ref": str, "attributes": {}}` where `sku_ref` matches a `sku_id` in
  `catalogue_seed.jsonl`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/test_verticals_pack.py`:

```python
import json

GST_RATES = {"cement": (18, "2523"), "tmt": (18, "7214"),
             "structural_steel": (18, "7216"), "tiles": (18, "6907"),
             "plywood": (18, "4412"), "wire": (18, "8544"),
             "pipe_pvc": (18, "3917"), "paint": (18, "3208")}


def _read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8")
            .splitlines() if line.strip()]


class CatalogueSeedTests(unittest.TestCase):
    def setUp(self):
        self.rows = _read_jsonl(PACK_DIR / "catalogue_seed.jsonl")

    def test_has_at_least_150_skus(self):
        self.assertGreaterEqual(len(self.rows), 150)

    def test_sku_ids_are_unique(self):
        ids = [r["sku_id"] for r in self.rows]
        self.assertEqual(len(ids), len(set(ids)))

    def test_no_row_carries_a_price_field(self):
        for r in self.rows:
            for banned in ("cost_price", "selling_rate", "opening_cost_per_kg",
                           "landed_cost_per_kg", "rate", "price"):
                self.assertNotIn(banned, r, r["sku_id"])

    def test_gst_and_hsn_match_gst_map_by_family(self):
        for r in self.rows:
            family = r["family"]
            self.assertIn(family, GST_RATES, r["sku_id"])
            rate, hsn = GST_RATES[family]
            self.assertEqual(r["gst_rate"], rate, r["sku_id"])
            self.assertEqual(r["hsn"], hsn, r["sku_id"])

    def test_every_row_has_required_fields(self):
        for r in self.rows:
            for field in ("sku_id", "canonical", "family", "brand", "attributes",
                          "default_unit", "units", "gst_rate", "hsn", "aliases"):
                self.assertIn(field, r, f"{r.get('sku_id')} missing {field}")
            self.assertIn(r["default_unit"], r["units"], r["sku_id"])
            self.assertGreater(len(r["aliases"]), 0, r["sku_id"])

    def test_tmt_rows_use_real_grades_and_diameters(self):
        tmt = [r for r in self.rows if r["family"] == "tmt"]
        self.assertGreater(len(tmt), 0)
        for r in tmt:
            self.assertIn(r["attributes"]["grade"], ("Fe500", "Fe500D", "Fe550"), r["sku_id"])
            self.assertIn(r["attributes"]["diameter_mm"], (8, 10, 12, 16, 20, 25), r["sku_id"])

    def test_cement_rows_use_real_types(self):
        cement = [r for r in self.rows if r["family"] == "cement"]
        self.assertGreater(len(cement), 0)
        for r in cement:
            self.assertIn(r["attributes"]["type"], ("OPC 43", "OPC 53", "PPC", "PSC"), r["sku_id"])

    def test_brands_are_from_the_real_indian_roster(self):
        allowed = {"UltraTech", "Ambuja", "ACC", "Shree", "Dalmia",
                  "Tata Tiscon", "JSW Neosteel", "SAIL", "Vizag",
                  "Havells", "Polycab", "Finolex", "RR Kabel",
                  "Century", "Greenply", "Kajaria", "Somany",
                  "Supreme", "Astral", "Finolex", "Asian Paints", "Berger",
                  "Nerolac", "Dulux", "JK", "JK Lakshmi"}
        for r in self.rows:
            self.assertIn(r["brand"], allowed, r["sku_id"])

    def test_aliases_include_a_hindi_or_romanized_spoken_form(self):
        romanized_markers = ("saria", "sariya", "bori", "bora", "cement",
                             "tar", "seet", "pata", "mota", "patla", "rang",
                             "pipe", "tile", "wire", "ply")
        rows_with_marker = [r for r in self.rows if any(
            any(marker in a.lower() for marker in romanized_markers)
            for a in r["aliases"])]
        self.assertGreater(len(rows_with_marker), len(self.rows) * 0.5)


class AliasPriorsTests(unittest.TestCase):
    def test_every_alias_prior_resolves_to_a_real_sku(self):
        catalogue_ids = {r["sku_id"] for r in _read_jsonl(PACK_DIR / "catalogue_seed.jsonl")}
        priors = _read_jsonl(PACK_DIR / "alias_priors.jsonl")
        self.assertGreater(len(priors), 0)
        for p in priors:
            self.assertIn(p["sku_ref"], catalogue_ids, p["phrase"])

    def test_no_duplicate_phrases(self):
        priors = _read_jsonl(PACK_DIR / "alias_priors.jsonl")
        phrases = [p["phrase"] for p in priors]
        self.assertEqual(len(phrases), len(set(phrases)))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && DATABASE_URL= PYTHONIOENCODING=utf-8 ../venv/Scripts/python.exe -m unittest test_verticals_pack -v`
Expected: FAIL — files absent.

- [ ] **Step 3: Author the data**

Write `verticals/hardware/catalogue_seed.jsonl`, ~150 rows across cement,
TMT, structural steel, wire, plywood, tiles, PVC pipe, paint. Use
`verticals/hardware/gst_map.yaml` for every `gst_rate`/`hsn` pair (all eight
categories are 18% per that file — cement `2523`, tmt `7214`,
structural_steel `7216`, tiles `6907`, plywood `4412`, wire `8544`, pipe_pvc
`3917`, paint `3208`). Real brands and Indian standard grades/sizes only
(spec: OPC 43/53, PPC, PSC; TMT Fe500/Fe500D/Fe550 in 8/10/12/16/20/25mm; wire
0.75/1/1.5/2.5/4/6 sqmm; plywood MR/BWR/BWP). No price fields. Each row
includes Hindi/romanized aliases (sariya, bori, patla, mota, etc).

Write `verticals/hardware/alias_priors.jsonl` with 60-100 high-value spoken
phrases mapped to `sku_ref`, covering common family-level and variant-level
utterances not already covered by in-catalogue aliases (e.g. "chhota
sariya" -> the 8mm Fe500 SKU, "bori cement" -> a default 50kg OPC 43 bag).

This step is expected to take multiple passes: draft with a Haiku subagent per
category (cement, tmt+structural, wire, plywood, tiles, pipe, paint), then
manually cross-check GST/HSN and brand/grade validity against
`verticals/hardware/gst_map.yaml` and this plan's allowed-brand list before
merging into the two files.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && DATABASE_URL= PYTHONIOENCODING=utf-8 ../venv/Scripts/python.exe -m unittest test_verticals_pack -v`
Expected: PASS, all tests in the file.

- [ ] **Step 5: Commit**

```bash
git add verticals/hardware/catalogue_seed.jsonl verticals/hardware/alias_priors.jsonl backend/test_verticals_pack.py
git commit -m "feat(hardware-pack): author ~150 SKU catalogue seed and alias priors"
```

---

### Task 3: `load_pack()` with validation

**Files:**
- Modify: `backend/verticals.py`
- Test: `backend/test_verticals.py` (extend)

**Interfaces:**
- Consumes: `verticals/hardware/*.yaml`, `*.jsonl` from Task 1-2.
- Produces: `verticals.load_pack(vertical_id: str, version: str) -> dict` with
  keys `meta, units, attributes, reports, catalogue (list), alias_priors
  (list)`. Raises `verticals.PackValidationError` on unknown units, missing
  GST, or alias collisions. Cached per `(vertical_id, version)` in a
  module-level dict; `verticals._PACK_CACHE.clear()` for test isolation.

- [ ] **Step 1: Write the failing test**

Append to `backend/test_verticals.py`:

```python
class LoadPackTests(unittest.TestCase):
    def setUp(self):
        verticals._PACK_CACHE.clear()

    def test_loads_the_hardware_pack(self):
        pack = verticals.load_pack("hardware", "1.0.0")
        self.assertEqual(pack["meta"]["vertical_id"], "hardware")
        self.assertGreaterEqual(len(pack["catalogue"]), 150)
        self.assertGreater(len(pack["alias_priors"]), 0)

    def test_unknown_vertical_raises(self):
        with self.assertRaises(verticals.PackValidationError):
            verticals.load_pack("nonexistent", "1.0.0")

    def test_second_load_is_cached(self):
        first = verticals.load_pack("hardware", "1.0.0")
        second = verticals.load_pack("hardware", "1.0.0")
        self.assertIs(first, second)

    def test_rejects_pack_with_unknown_unit(self):
        import copy
        pack = copy.deepcopy(verticals.load_pack("hardware", "1.0.0"))
        pack["catalogue"][0]["default_unit"] = "furlong"
        with self.assertRaises(verticals.PackValidationError):
            verticals._validate_pack(pack)

    def test_rejects_pack_missing_gst(self):
        import copy
        pack = copy.deepcopy(verticals.load_pack("hardware", "1.0.0"))
        del pack["catalogue"][0]["gst_rate"]
        with self.assertRaises(verticals.PackValidationError):
            verticals._validate_pack(pack)

    def test_rejects_alias_collision_across_families(self):
        import copy
        pack = copy.deepcopy(verticals.load_pack("hardware", "1.0.0"))
        cement = next(r for r in pack["catalogue"] if r["family"] == "cement")
        tmt = next(r for r in pack["catalogue"] if r["family"] == "tmt")
        cement["aliases"] = list(cement["aliases"]) + ["__collision_probe__"]
        tmt["aliases"] = list(tmt["aliases"]) + ["__collision_probe__"]
        with self.assertRaises(verticals.PackValidationError):
            verticals._validate_pack(pack)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && DATABASE_URL= PYTHONIOENCODING=utf-8 ../venv/Scripts/python.exe -m unittest test_verticals -v`
Expected: FAIL — `load_pack` does not exist.

- [ ] **Step 3: Write minimal implementation**

Note: an alias is only a collision when it maps to SKUs in **different
families** — many real hardware aliases (e.g. brand names) legitimately point
at multiple SKUs of the same family and get disambiguated downstream by
`matcher.resolve_variant`. Cross-family collisions are the real defect (a
shipped pack must never send "cement" ambiguously toward a TMT SKU).

Add to `backend/verticals.py`:

```python
import json
from pathlib import Path

import yaml

PACK_ROOT = Path(__file__).resolve().parent.parent / "verticals"
_PACK_CACHE: dict = {}


class PackValidationError(Exception):
    pass


def _read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _read_jsonl(path: Path) -> list:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _validate_pack(pack: dict) -> None:
    known_units = set(pack["units"].keys())
    alias_owner: dict[str, tuple[str, str]] = {}  # alias -> (sku_id, family)
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && DATABASE_URL= PYTHONIOENCODING=utf-8 ../venv/Scripts/python.exe -m unittest test_verticals -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite to check for regressions**

Run: `cd backend && DATABASE_URL= PYTHONIOENCODING=utf-8 ../venv/Scripts/python.exe -m unittest discover -s . -p 'test_*.py'`
Expected: no fewer passes than the 223 baseline (this task adds tests, so the count grows).

- [ ] **Step 6: Commit**

```bash
git add backend/verticals.py backend/test_verticals.py
git commit -m "feat(verticals): add load_pack with unit/GST/alias validation"
```

(Task 4 depends on `verticals/hardware/prompt_fragment.md` existing — see Task 6, which must land before this task's `load_pack` test suite is run against a committed tree. If sequencing in a single session, write a minimal `prompt_fragment.md` placeholder now and let Task 6 replace its content.)

---

### Task 4: `seed_tenant()` — copy pack into a tenant

**Files:**
- Modify: `backend/verticals.py`
- Test: `backend/test_verticals.py` (extend)

**Interfaces:**
- Consumes: `load_pack()` from Task 3; a `Repo`-shaped object (`repo.py:Repo`)
  with `upsert_sku(sku: dict)`, `save_config(patch: dict)`, and `db.connect()`
  from `backend/db.py` for the global `vertical_priors` table (only used when
  `db.is_configured()` is true — the JsonRepo test path skips DB writes and
  returns priors via the pack's own `alias_priors` at read time instead, see
  Task 5).
- Produces: `verticals.seed_tenant(repo, vertical_id: str, version: str = "1.0.0") -> int`
  returning the count of SKUs seeded. Idempotent: seeding twice does not
  duplicate SKUs (sku_id is the natural key `upsert_sku` already dedupes on).

- [ ] **Step 1: Write the failing test**

Append to `backend/test_verticals.py`:

```python
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import repo as repo_mod  # noqa: E402


class SeedTenantTests(unittest.TestCase):
    def setUp(self):
        verticals._PACK_CACHE.clear()
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = repo_mod.JsonRepo(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_seeds_every_catalogue_row_as_a_sku(self):
        pack = verticals.load_pack("hardware", "1.0.0")
        count = verticals.seed_tenant(self.repo, "hardware", "1.0.0")
        self.assertEqual(count, len(pack["catalogue"]))
        self.assertGreaterEqual(len(self.repo.load_catalogue()), 150)

    def test_seeded_skus_carry_no_price_fields(self):
        verticals.seed_tenant(self.repo, "hardware", "1.0.0")
        for sku in self.repo.load_catalogue():
            self.assertNotIn("cost_price", sku)
            self.assertNotIn("selling_rate", sku)

    def test_stamps_tenant_vertical_config(self):
        verticals.seed_tenant(self.repo, "hardware", "1.0.0")
        cfg = self.repo.load_config()
        self.assertEqual(verticals.tenant_vertical(cfg), ("hardware", "1.0.0"))

    def test_seeding_twice_does_not_duplicate_skus(self):
        verticals.seed_tenant(self.repo, "hardware", "1.0.0")
        before = len(self.repo.load_catalogue())
        verticals.seed_tenant(self.repo, "hardware", "1.0.0")
        after = len(self.repo.load_catalogue())
        self.assertEqual(before, after)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && DATABASE_URL= PYTHONIOENCODING=utf-8 ../venv/Scripts/python.exe -m unittest test_verticals -v`
Expected: FAIL — `seed_tenant` does not exist.

- [ ] **Step 3: Write minimal implementation**

Add to `backend/verticals.py`:

```python
def seed_tenant(repo, vertical_id: str, version: str = "1.0.0") -> int:
    """Copy a vertical pack's catalogue into `repo`'s tenant and record the
    choice in tenant config.

    Global vertical_priors (spoken-form -> sku_ref, shared across all tenants
    on this vertical/version) are shipped data, not tenant data — they live in
    the pack itself and are read directly by the matcher via
    `load_pack()[...]["alias_priors"]`, never copied per-tenant. This function
    therefore only writes to the tenant's own catalogue and config.
    """
    pack = load_pack(vertical_id, version)
    count = 0
    for row in pack["catalogue"]:
        sku = dict(row)
        sku.pop("hsn", None)  # HSN lands in attributes per foundation contract
        attrs = dict(sku.get("attributes") or {})
        if "hsn" in row:
            attrs.setdefault("hsn", row["hsn"])
        sku["attributes"] = attrs
        repo.upsert_sku(sku)
        count += 1
    cfg = repo.load_config()
    repo.save_config(set_tenant_vertical(cfg, vertical_id, version))
    return count
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && DATABASE_URL= PYTHONIOENCODING=utf-8 ../venv/Scripts/python.exe -m unittest test_verticals -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/verticals.py backend/test_verticals.py
git commit -m "feat(verticals): add seed_tenant to copy a pack's catalogue into a tenant"
```

---

### Task 5: matcher `vertical_prior` stage

**Files:**
- Modify: `backend/matcher.py` (`match()` function only — new stage, no
  reordering of existing stages)
- Test: `backend/test_matcher.py` (extend if it exists, else create
  `backend/test_matcher_vertical_prior.py`)

**Interfaces:**
- Consumes: `pack["alias_priors"]` shape `{"phrase": str, "sku_ref": str,
  "attributes": {}}` from Task 3/4; `match(phrase, catalogue, learning, flow,
  vertical_priors=None)`.
- Produces: `matcher.match(..., vertical_priors: list | None = None)` — a new
  optional parameter, default `None` so every existing call site (which never
  passes it) is unaffected. When given, priors are consulted strictly after
  shop aliases and shop learned priors (the existing Stage 2 / `alias_idx`,
  which already merges catalogue aliases and `learning.aliases_learned`) and
  strictly before Stage 2b (attribute inference) and Stage 3 (fuzzy).

- [ ] **Step 1: Write the failing test**

Check first whether `backend/test_matcher.py` exists:

Run: `cd backend && ls test_matcher.py 2>/dev/null || echo none`

If it exists, append the class below to it; otherwise create
`backend/test_matcher_vertical_prior.py` with the same class plus its own
`import matcher as M` and `if __name__ == "__main__": unittest.main()`.

```python
class VerticalPriorStageTests(unittest.TestCase):
    """A shop's own vocabulary must always beat a shipped prior (spec 3.4)."""

    CATALOGUE = [
        {"sku_id": "CEM_A", "canonical": "UltraTech OPC 43 Cement 50kg",
         "family": "cement", "attributes": {"type": "OPC 43", "brand": "UltraTech"},
         "default_unit": "bag", "units": {"bag": 1}, "aliases": ["ultratech opc"]},
        {"sku_id": "CEM_B", "canonical": "Ambuja PPC Cement 50kg",
         "family": "cement", "attributes": {"type": "PPC", "brand": "Ambuja"},
         "default_unit": "bag", "units": {"bag": 1}, "aliases": ["ambuja ppc"]},
    ]
    PRIORS = [{"phrase": "gharelu cement", "sku_ref": "CEM_A", "attributes": {}}]

    def _empty_learning(self):
        return {"aliases_learned": [], "attribute_priors": [], "unit_priors": [],
                "corrections": []}

    def test_vertical_prior_resolves_a_phrase_no_shop_alias_covers(self):
        result = M.match("gharelu cement", self.CATALOGUE, self._empty_learning(),
                          vertical_priors=self.PRIORS)
        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["sku_id"], "CEM_A")
        self.assertEqual(result["stage"], "vertical_prior")

    def test_shop_learned_alias_outranks_a_conflicting_vertical_prior(self):
        learning = self._empty_learning()
        learning["aliases_learned"] = [{"phrase": "gharelu cement", "sku_id": "CEM_B"}]
        result = M.match("gharelu cement", self.CATALOGUE, learning,
                          vertical_priors=self.PRIORS)
        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["sku_id"], "CEM_B")
        self.assertEqual(result["stage"], "alias")

    def test_absent_vertical_priors_do_not_change_existing_behaviour(self):
        result = M.match("ultratech opc", self.CATALOGUE, self._empty_learning())
        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["sku_id"], "CEM_A")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && DATABASE_URL= PYTHONIOENCODING=utf-8 ../venv/Scripts/python.exe -m unittest test_matcher_vertical_prior -v` (or the class inside `test_matcher.py`)
Expected: FAIL — `match()` has no `vertical_priors` parameter, `TypeError`.

- [ ] **Step 3: Write minimal implementation**

In `backend/matcher.py`, change the `match()` signature and insert the new
stage. Only these two edits — everything else in the function is unchanged:

```python
def match(phrase: str, catalogue: list, learning: dict, flow: str = "live_sale",
          vertical_priors: Optional[list] = None) -> dict:
```

Insert immediately after the existing Stage 2 block (the `if hit_ids:` block
that returns on a shop-alias hit) and before the `# Stage 2b` comment:

```python
    # Stage "vertical_prior" — shipped spoken-form priors for this vertical,
    # strictly beneath shop aliases and shop learned priors (both already
    # checked above via alias_idx, which merges catalogue aliases and
    # learning.aliases_learned). A shop's own vocabulary always wins; this
    # stage only fires when nothing shop-specific matched.
    if vertical_priors:
        vp_idx: dict = {}
        for vp in vertical_priors:
            key = normalize(str(vp.get("phrase") or ""))
            ref = vp.get("sku_ref")
            if key and ref in by_id:
                vp_idx.setdefault(key, []).append(ref)
        vp_hit = vp_idx.get(norm)
        if vp_hit is None:
            padded_vp = f" {norm} "
            for a in sorted((a for a in vp_idx if " " in a), key=len, reverse=True):
                if f" {a} " in padded_vp:
                    vp_hit = vp_idx[a]
                    break
        if vp_hit:
            uniq_vp = list(dict.fromkeys(vp_hit))
            if len(uniq_vp) == 1:
                return {"status": "matched", "sku_id": uniq_vp[0], "confidence": 0.9,
                        "assumed": {}, "stage": "vertical_prior"}
            res = resolve_variant(uniq_vp, by_id, spoken_attrs, learning)
            res["stage"] = "vertical_prior_family"
            return res
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && DATABASE_URL= PYTHONIOENCODING=utf-8 ../venv/Scripts/python.exe -m unittest test_matcher_vertical_prior -v`
Expected: PASS, 3 tests.

- [ ] **Step 5: Run the full suite**

Run: `cd backend && DATABASE_URL= PYTHONIOENCODING=utf-8 ../venv/Scripts/python.exe -m unittest discover -s . -p 'test_*.py'`
Expected: baseline count or higher, no regressions — `vertical_priors` defaults to `None` so every existing caller of `match()` is untouched.

- [ ] **Step 6: Commit**

```bash
git add backend/matcher.py backend/test_matcher_vertical_prior.py
git commit -m "feat(matcher): add vertical_prior stage beneath shop-specific matching"
```

---

### Task 6: prompt_fragment.md and samvaad_config composition

**Files:**
- Create: `verticals/hardware/prompt_fragment.md` (replaces the Task 3
  placeholder with real content)
- Modify: `backend/samvaad_config.py`
- Test: `backend/test_samvaad_config.py` (create, or extend if it exists)

**Interfaces:**
- Consumes: `verticals.load_pack()["prompt_fragment"]`.
- Produces: `samvaad_config.build_prompt(vertical_id: str | None = None,
  version: str | None = None) -> str` returning `INSTRUCTIONS` unchanged when
  no vertical is given, or `INSTRUCTIONS + "\n\n" + prompt_fragment` when one
  is. The 27-tool registry (`agent.TOOLS`) is never touched by this function.

- [ ] **Step 1: Write the failing test**

Run: `cd backend && ls test_samvaad_config.py 2>/dev/null || echo none` first.

Create/extend with:

```python
import unittest

import samvaad_config


class BuildPromptTests(unittest.TestCase):
    def test_no_vertical_returns_base_instructions_only(self):
        prompt = samvaad_config.build_prompt()
        self.assertEqual(prompt, samvaad_config.INSTRUCTIONS)

    def test_hardware_vertical_appends_the_pack_fragment(self):
        prompt = samvaad_config.build_prompt("hardware", "1.0.0")
        self.assertTrue(prompt.startswith(samvaad_config.INSTRUCTIONS))
        self.assertIn("hardware", prompt.lower())
        self.assertGreater(len(prompt), len(samvaad_config.INSTRUCTIONS))

    def test_unknown_vertical_falls_back_to_base_instructions(self):
        prompt = samvaad_config.build_prompt("nonexistent", "1.0.0")
        self.assertEqual(prompt, samvaad_config.INSTRUCTIONS)

    def test_tool_registry_is_unaffected_by_vertical_choice(self):
        import agent
        before = list(agent.TOOLS)
        samvaad_config.build_prompt("hardware", "1.0.0")
        self.assertEqual(agent.TOOLS, before)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && DATABASE_URL= PYTHONIOENCODING=utf-8 ../venv/Scripts/python.exe -m unittest test_samvaad_config -v`
Expected: FAIL — `build_prompt` does not exist.

- [ ] **Step 3: Write the prompt fragment and the composition function**

`verticals/hardware/prompt_fragment.md`:

```markdown
HARDWARE VERTICAL CONTEXT:
Ye dukaan cement, TMT sariya, structural steel, wire, plywood, tiles, PVC
pipe aur paint bechti hai. Jab owner in categories mein se koi cheez bole,
farz karo woh saari catalogue mein already seeded hai — pehle usse dhundo,
naya add karne se pehle. Grade, size aur brand ke common spoken forms
pehchano: "sariya" ya "rod" TMT ke liye, "bori" cement bag ke liye, "patla"
chhote diameter TMT ke liye, "mota" bade diameter ke liye.
```

In `backend/samvaad_config.py`, after the `INSTRUCTIONS` string definition,
add:

```python
def build_prompt(vertical_id: str | None = None, version: str | None = None) -> str:
    """Compose the base Samvaad prompt with a vertical pack's fragment.

    The 27-tool registry (agent.TOOLS) is never touched here — only the text
    instructions change, per spec section 3.5.
    """
    if not vertical_id or not version:
        return INSTRUCTIONS
    import verticals
    try:
        pack = verticals.load_pack(vertical_id, version)
    except verticals.PackValidationError:
        return INSTRUCTIONS
    return INSTRUCTIONS + "\n\n" + pack["prompt_fragment"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && DATABASE_URL= PYTHONIOENCODING=utf-8 ../venv/Scripts/python.exe -m unittest test_samvaad_config -v`
Expected: PASS, 4 tests.

- [ ] **Step 5: Re-run Task 3's `load_pack` suite now that `prompt_fragment.md` has real content**

Run: `cd backend && DATABASE_URL= PYTHONIOENCODING=utf-8 ../venv/Scripts/python.exe -m unittest test_verticals test_verticals_pack -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add verticals/hardware/prompt_fragment.md backend/samvaad_config.py backend/test_samvaad_config.py
git commit -m "feat(samvaad): compose base prompt with vertical pack fragment"
```

---

### Task 7: Onboarding wiring

**Files:**
- Modify: `frontend/index.html` (only within `<!-- @section:onboarding -->` /
  `<!-- @endsection:onboarding -->`)
- Modify: `backend/main.py` (or wherever the onboarding endpoint lives — locate
  first with `grep -n "onboard" backend/main.py`)
- Test: `backend/test_onboarding_vertical.py` (create)

**Interfaces:**
- Consumes: `verticals.seed_tenant(repo, vertical_id, version)` from Task 4.
- Produces: an onboarding request path that, given a selected vertical,
  seeds the tenant's catalogue synchronously and records the vertical in
  config, so a fresh signup can voice-sell a seeded SKU immediately (spec
  3.7).

- [ ] **Step 1: Locate the onboarding endpoint**

Run: `cd backend && grep -n "onboard" main.py`

Read the matched function(s) fully before writing the test, so the test
targets the real request/response shape (this codebase uses FastAPI's
`TestClient`, consistent with the pattern already used in
`backend/test_agent.py`/`backend/test_store.py` — confirm the exact import
path by reading one of those files' top-of-file imports first).

- [ ] **Step 2: Write the failing test**

Create `backend/test_onboarding_vertical.py` using the exact endpoint path
and auth pattern found in Step 1 (do not guess the route — copy the pattern
from an existing test that hits an authenticated endpoint, e.g. whichever
test in `test_agent.py` sets up a logged-in `TestClient` session). The test
must assert:

```python
# after completing onboarding with vertical="hardware":
# 1. GET the catalogue endpoint (or repo.load_catalogue() directly against
#    the same data dir the app used) returns >= 150 SKUs
# 2. the tenant's config reports vertical_id == "hardware"
```

Write out the concrete test body once Step 1's read confirms the exact
function names and request shape — this plan intentionally does not guess
FastAPI route strings that may not match the real file.

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && DATABASE_URL= PYTHONIOENCODING=utf-8 ../venv/Scripts/python.exe -m unittest test_onboarding_vertical -v`
Expected: FAIL — seeding not wired yet.

- [ ] **Step 4: Wire seeding into the onboarding handler**

In the onboarding handler located in Step 1, after the existing onboarding
persistence call, add:

```python
import verticals
# ... inside the handler, given the request's chosen vertical_id (default "hardware"):
try:
    verticals.seed_tenant(repo, vertical_id, "1.0.0")
except verticals.PackValidationError:
    pass  # never fail signup because a pack is malformed; log and move on
```

In `frontend/index.html`, inside `<!-- @section:onboarding -->`, add a single-
option vertical control (hardware only at launch — spec 3.6: "a single-option
control that records the choice rather than a chooser with one item
pretending to be a menu") that submits `vertical_id: "hardware"` with the
existing onboarding request. Match the existing markup/JS conventions in that
section (read the surrounding block before inserting).

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && DATABASE_URL= PYTHONIOENCODING=utf-8 ../venv/Scripts/python.exe -m unittest test_onboarding_vertical -v`
Expected: PASS.

- [ ] **Step 6: Run the full suite**

Run: `cd backend && DATABASE_URL= PYTHONIOENCODING=utf-8 ../venv/Scripts/python.exe -m unittest discover -s . -p 'test_*.py'`
Expected: no regressions.

- [ ] **Step 7: Verify index.html still renders**

Run: `cd .. && ./venv/Scripts/python.exe -c "import sys; sys.path.insert(0,'backend'); import app; from fastapi.testclient import TestClient; c=TestClient(app.app); r=c.get('/'); print(r.status_code, len(r.text))"`
Expected: `200`.

- [ ] **Step 8: Commit**

```bash
git add frontend/index.html backend/main.py backend/test_onboarding_vertical.py
git commit -m "feat(onboarding): seed the hardware vertical pack on signup"
```

---

### Task 8: Twenty-phrase resolution success test (spec 3.7)

**Files:**
- Test: `backend/test_hardware_vertical_resolution.py` (create)

**Interfaces:**
- Consumes: `verticals.seed_tenant`, `verticals.load_pack`, `matcher.match`.
- Produces: nothing new — this is the acceptance test for the whole
  sub-project, run against a freshly seeded `JsonRepo` tenant.

- [ ] **Step 1: Write the test**

```python
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
        self.assertGreaterEqual(resolved, 16,
                                f"unresolved: {unresolved}")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test**

Run: `cd backend && DATABASE_URL= PYTHONIOENCODING=utf-8 ../venv/Scripts/python.exe -m unittest test_hardware_vertical_resolution -v`
Expected: PASS. If any phrase fails, the fix is adding/adjusting an alias or
alias_prior in Task 2's data files (re-run Task 2's tests after), not
loosening this test's threshold below 16/20.

- [ ] **Step 3: Run the full suite one final time**

Run: `cd backend && DATABASE_URL= PYTHONIOENCODING=utf-8 ../venv/Scripts/python.exe -m unittest discover -s . -p 'test_*.py'`
Expected: baseline (223) plus every test added in Tasks 1-8, all passing.

- [ ] **Step 4: Commit**

```bash
git add backend/test_hardware_vertical_resolution.py
git commit -m "test(hardware-vertical): twenty-phrase resolution acceptance test"
```

---

### Task 9: REVIEW.md and final sweep

**Files:**
- Create: `verticals/hardware/REVIEW.md`

**Interfaces:**
- Produces: a human-reviewable table of every SKU in `catalogue_seed.jsonl`.

- [ ] **Step 1: Generate the table**

Write a one-off script (do not commit it) that reads
`verticals/hardware/catalogue_seed.jsonl` and emits a Markdown table with
columns: `sku_id | canonical | family | brand | key attributes | default_unit
| gst_rate | hsn`. Run it with the venv python and redirect into
`verticals/hardware/REVIEW.md`, prefixed with a short header noting the pack
version, row count, and instructions for a human reviewer (spot-check grade/
brand/GST against `gst_map.yaml`).

- [ ] **Step 2: Manually re-check a sample**

Cross-check at least 10 rows spanning all 8 families against
`verticals/hardware/gst_map.yaml` and this plan's brand roster by hand
(Read the file, do not trust the generation script).

- [ ] **Step 3: Commit**

```bash
git add verticals/hardware/REVIEW.md
git commit -m "docs(hardware-pack): add SKU review table for human sign-off"
```

---

## Exit gate

- `cd backend && DATABASE_URL= PYTHONIOENCODING=utf-8 ../venv/Scripts/python.exe -m unittest discover -s . -p 'test_*.py'` passes with no regressions from the 223 baseline.
- `verticals/hardware/` contains all eight files listed in spec 3.2.
- `verticals/hardware/REVIEW.md` lists every seeded SKU for human sign-off.
- The twenty-phrase resolution test (Task 8) passes at >=16/20.
