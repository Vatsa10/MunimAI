# Munim.ai — Vertical Strategy & Competitive Plan (India)

## 1. Core strategic thesis

Munim.ai does not win on features. It wins on **data-entry cost collapse in
high-SKU-ambiguity, high-transaction-frequency, low-literacy-tolerance
businesses.**

Voice ROI is a function of three variables:

```
Voice_ROI ≈ (SKU_ambiguity × txn_frequency × hands_busy_factor)
            / (ambient_noise × ticket_size_trust_barrier)
```

Any vertical that scores high on the numerator and low on the denominator is a
target. Everything else is a distraction.

**Positioning:** compete against the paper diary and the WhatsApp-photo
workflow, not against Vyapar's feature grid. Vyapar wins any feature-parity
comparison; it cannot win a "never touch a screen" comparison.

---

## 2. Vertical ranking for India

Scored 1–5. Higher total = better initial fit.

| Vertical | SKU ambiguity | Txn freq | Hands busy | Credit intensity | Noise (inverse) | Ticket trust | **Total** |
|---|---|---|---|---|---|---|---|
| **Building materials / cement / steel / hardware wholesale** | 5 | 4 | 5 | 5 | 3 | 3 | **25** |
| **Agri-input (seeds, fertiliser, pesticide)** | 5 | 4 | 4 | 5 | 4 | 4 | **26** |
| **Pharma retail / medical store** | 5 | 5 | 4 | 3 | 4 | 4 | **25** |
| **Auto parts / two-wheeler spares** | 5 | 4 | 5 | 4 | 3 | 4 | **25** |
| **Electrical & plumbing (sanitaryware, pipes, wire)** | 5 | 4 | 5 | 4 | 3 | 4 | **25** |
| Textile / garment wholesale | 4 | 4 | 3 | 5 | 3 | 3 | 22 |
| FMCG distributor / kirana wholesale | 3 | 5 | 4 | 5 | 3 | 4 | 24 |
| Kirana retail (B2C) | 2 | 5 | 3 | 4 | 3 | 5 | 22 |
| Restaurant / QSR | 2 | 5 | 4 | 1 | 1 | 5 | 18 |
| Jewellery | 3 | 2 | 2 | 2 | 5 | 1 | 15 |

### 2.1 The four verticals to build

**Rank 1 — Building materials & hardware wholesale (LAUNCH VERTICAL)**

- Turnover band: ₹1–10 Cr, tier-2/tier-3.
- Why: highest ambiguity ("53 grade OPC", "8mm TMT Fe500D", "1.5sqmm 90m
  coil"), unit chaos (bag/tonne/quintal/bundle/running-foot), extreme credit
  (30–90 day contractor udhaar), owner physically on the floor.
- Barrier: Vyapar already claims near-monopoly here. You are not displacing
  Vyapar users — you are taking the ~55–60% still on the diary, plus Vyapar
  users whose *staff* refuse to enter data.
- Note: verify Vyapar's stated hardware dominance independently before
  committing; treat the ~18–22% niche share figure as directional.

**Rank 2 — Agri-input retail (HIGHEST STRUCTURAL FIT)**

- Turnover band: ₹50L–5Cr, tier-3/rural.
- Why: lowest English literacy of any target vertical, highest voice
  necessity, seasonal credit cycle (sow-now-pay-at-harvest) that maps exactly
  onto your receivables + FIFO payment allocation model, quieter premises than
  a hardware godown.
- Barrier: batch/expiry/licence compliance (Insecticides Act), sharper price
  sensitivity, and connectivity — **offline-first is non-negotiable here**.
- This is arguably the better beachhead if you can absorb offline-first early.

**Rank 3 — Auto parts / two-wheeler spares**

- Why: part-number hell is the single strongest case for learned per-shop
  aliases. "Bajaj Pulsar 150 ka clutch plate" → OEM SKU is a resolution problem
  no keyboard UI solves well.
- Barrier: fitment/compatibility data is a hard cold-start problem; noise.

**Rank 4 — Electrical & plumbing / sanitaryware**

- Why: near-identical operating shape to building materials — same units, same
  credit, same brand-grade-size ambiguity. Cheapest possible second vertical
  because it reuses ~80% of the hardware template.

**Explicitly deprioritise:** pharma (Schedule H, batch/expiry, DL number,
21 CFR-grade audit expectations, and a legacy incumbent in Marg — high build
cost, high regulatory tail), restaurants (noise floor kills voice), jewellery
(trust barrier on ticket size is fatal), kirana B2C (SKU ambiguity too low —
barcode beats voice).

---

## 3. Vertical templates: architecture

Do **not** fork the codebase per vertical. Build a **Vertical Pack** as data +
config, loaded per tenant.

### 3.1 Vertical Pack contents

```
verticals/
  hardware/
    catalogue_seed.jsonl        # 800–1500 pre-built SKUs w/ brand, grade, size
    alias_priors.jsonl          # spoken forms → SKU, seeded from field recordings
    units.yaml                  # bag/tonne/bundle/rft + conversion factors
    attributes.yaml             # grade, diameter, brand, finish, length
    gst_map.yaml                # HSN + rate defaults per category
    prompts/                    # vertical-specific Samvaad prompt fragments
    reports.yaml                # which dashboards matter (frozen capital, contractor ageing)
    doc_templates/              # invoice/challan/quote layouts
    compliance.yaml             # e-way bill thresholds, mandatory fields
```

### 3.2 Component-level changes required

- `backend/matcher.py` — add a `vertical_priors` resolution layer beneath
  learned per-shop aliases. Resolution order becomes:
  `shop_alias → shop_learned_prior → vertical_prior → substring/SKU → fuzzy`.
- `backend/ledger.py` — unit conversion table becomes vertical-scoped rather
  than global.
- `backend/samvaad_config.py` — prompt generation composes a base prompt plus
  a vertical fragment; keep the 27-tool registry unchanged.
- `user_config` table — add `vertical_id`, `vertical_pack_version`.
- New `vertical_priors` table, read-only per tenant, versioned and shipped by
  you (never written by a tenant; tenant corrections go to `learning` as today).

### 3.3 Why this matters commercially

Cold start is your worst onboarding metric. A generic system asks 12
clarification questions on day 1; a vertical-packed system asks 2. That is the
difference between a 3-minute time-to-first-value and churn.

**Target: owner records a real sale, by voice, within 3 minutes of signup,
with zero catalogue setup.** Vertical packs are the only way to hit this.

---

## 4. Feature plan: where you can actually beat Vyapar

### 4.1 Win outright (build and market hard)

| Feature | Why it wins |
|---|---|
| **Voice-first multi-item capture with self-correction** | No incumbent does conversational entry. This is the entire pitch. |
| **Code-mixed multilingual understanding** | Incumbents localise the *UI*; you understand the *speech*. Different category. |
| **Per-shop learned aliases (compounding)** | Only structural moat you have. Accuracy improves with usage, so switching cost rises monotonically. |
| **Supplier invoice → landed cost → stock, from a photo** | Removes the single most hated hour of the week. Directly attacks the WhatsApp-photo-to-accountant workflow. |
| **Frozen capital reporting** | Nobody in the SMB tier surfaces dead stock as a capital metric. High-status insight for the owner; excellent sales demo. |
| **Event-sourced ledger + backdated correction** | Sell as "you can fix last Tuesday and everything downstream self-corrects." Incumbents' mutable stock fields cannot. |
| **UNCOUNTED ≠ zero** | Honest stock state. Every diary-migrating shop has partially-known stock; incumbents force a bad zero. |
| **Voice-triggered WhatsApp credit reminders** | Collections uplift is the clearest ROI number you can put on a slide. |

### 4.2 Reach parity (table stakes — you lose deals without these)

- GST invoice + HSN/SAC + e-way bill above ₹50,000
- **Tally / Busy export (XML or CSV)** — CA gatekeeping; ship this early
- Delivery challan, quotation, proforma, purchase order
- Credit note / debit note and sales returns
- Multi-rate price lists (retail / contractor / dealer)
- Bulk catalogue import from Excel
- Thermal + A4 print, and a desktop/Windows path
- Batch/expiry (only if you enter agri or pharma)
- Multi-user with staff roles and per-role permissions

### 4.3 Concede (do not build)

- Full double-entry accounting, balance sheet, P&L filing
- Payroll, e-invoicing IRP integration at launch, e-commerce storefront
- Manufacturing BOM, job work
- Generic CRM

Concede publicly and cleanly: "Munim runs the shop floor; your Tally runs the
books." This is a stronger position than a weak accounting module.

### 4.4 Costing model — must fix before mid-market

Last-purchase/replacement-cost margin is acceptable for micro shops and will be
rejected by any CA above roughly ₹5 Cr turnover. Add **weighted-average as a
per-tenant configurable costing method**, with FIFO as a later option. Keep the
event ledger as the source; costing becomes a replay strategy, not a schema
change.

---

## 5. Offline-first and barcode — before mid-market

Both are currently unimplemented and both are **hard blockers**, not
enhancements. Sequence them ahead of any upmarket push.

### 5.1 Offline-first

**Why it is a blocker**

- Tier-3 and rural connectivity is intermittent; agri-input retail is
  effectively unusable without it.
- Incumbents ship offline as a baseline expectation — offline access is treated
  as essential for connectivity-challenged regions, and a shop that cannot bill
  during an outage will not adopt.
- Godowns and basements are dead zones inside otherwise-connected towns.

**Architecture**

- Your event-sourced ledger is *already* the correct substrate. Append-only
  events sync far more cleanly than mutable rows. This is the payoff for the
  design choice.
- Client store: IndexedDB (PWA) or SQLite (native shell). Local event log with
  client-generated ULIDs.
- Sync: outbox pattern, monotonic per-tenant sequence, server assigns
  authoritative ordering on receipt. Conflicts are rare because events are
  additive; the genuine conflict cases are stock-take events and product
  edits — resolve stock-takes by timestamp-wins, product edits by
  last-write-wins with an audit row.
- Derived state (stock, margin, dues) recomputed locally by a JS/WASM port of
  the replay logic, or by shipping a compact snapshot plus local delta replay.
  Prefer the snapshot+delta approach — do not fork the ledger logic into two
  languages.
- **Voice degrades gracefully:** offline mode falls back to on-device STT or a
  typed/tap quick-entry path. Do not block billing on voice availability. This
  needs an explicit offline UI state, not a silent failure.

**Scope boundary:** offline must cover sale entry, bill print, stock lookup,
and customer dues. It does not need to cover invoice digitisation, WhatsApp
send, or dashboards.

### 5.2 Barcode

**Why it is a blocker**

- Above ~2,000 SKUs or with counter staff, scanning beats speaking on both
  speed and accuracy. Voice is the entry method for the *owner*; barcode is the
  entry method for *staff*.
- Mid-market buyers treat its absence as disqualifying, regardless of voice
  quality.
- It is also your accuracy backstop: scan resolves the SKU deterministically
  when ambient noise defeats ASR.

**Architecture**

- Camera-based scanning in the PWA via `BarcodeDetector` with a ZXing/QuaggaJS
  fallback; USB HID scanners work as keyboard input with no extra work.
- Add `barcode` / `ean` columns to `skus`, indexed and tenant-scoped, with
  support for multiple barcodes per SKU (same product, different pack).
- Internal label generation for unbarcoded goods (most hardware and agri stock)
  — this is required, not optional, in these verticals.
- **Hybrid entry is the actual differentiator:** scan the item, speak the
  quantity. "Scan, bolo do bori" is faster than either method alone and is a
  demo nobody else can run.

### 5.3 Sequencing

| Phase | Scope | Gate to exit |
|---|---|---|
| 0 | Field ASR validation in 5 real shops at peak hours | WER acceptable under real noise |
| 1 | Hardware vertical pack, 25–50 design partners, tier-2 | 3-min time-to-first-value; gross margin per shop positive |
| 2 | Tally export, credit/debit notes, price lists, bulk import | CA-referred deals closing |
| 3 | **Offline-first** | Billing works through a 30-min outage, syncs clean |
| 4 | **Barcode + hybrid scan-and-speak** | Counter staff onboard without training |
| 5 | Staff roles, weighted-average costing, PO/GRN, returns | Mid-market (₹5–25 Cr) deals closing |
| 6 | Vertical packs 2–4: agri-input, electrical/plumbing, auto parts | Pack ships in <4 weeks each |

Do not start phase 5 before phases 3 and 4 are done. Mid-market without offline
and barcode is a guaranteed loss against GoFrugal, Marg, and Busy.

---

## 6. Open risks to validate

1. **Ambient-noise WER.** Single largest technical kill risk. Measure before
   anything else.
2. **Unit economics.** Voice-to-voice minutes plus document AI against a
   ₹999–1,499/mo ceiling. Model gross margin per shop-day; cap or tier voice
   minutes if it does not clear.
3. **Trust on large tickets.** Owners will not accept a voice-created ₹80,000
   invoice unseen. Confirm-before-write is correct and it reduces the time
   saved — measure the real saving, do not assume it.
4. **Distribution.** Indian SMB software sells through feet-on-street and CA
   referral networks; incumbents have thousands of local partners. Budget for a
   channel motion or accept a hard growth ceiling.
5. **Moat duration.** Multilingual voice APIs commoditise within roughly 12–24
   months. The learned per-shop alias graph is the only thing that survives
   that — instrument it, measure clarification-questions-per-session over
   tenant age, and make that curve your headline retention metric.

---

## 7. One-line positioning

> Munim.ai is the voice-first operating system for India's hardware and
> agri-input trade — the shop owner speaks, the ledger stays exact, and the
> diary disappears.

*Market figures on incumbents (user counts, share, tier-2/3 revenue mix) are
drawn from public secondary sources and vendor claims; verify independently
before using them in a fundraise deck.*
