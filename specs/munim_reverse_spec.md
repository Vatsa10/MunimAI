# Munim.ai / Munshi AI — Reverse Spec + Gap Analysis + Target Spec

Date: 2026-09-29. Method: every backend file, the single-file frontend, service worker, verticals pack, docs, and both decks were read; four analysts wrote per-layer notes with file:line evidence; findings merged here. `(F)` = fact from code, `(I)` = inference.

Test status: repo has 348 `def test_` in 25 files (F). I started a full run; it had not returned when this was written, so **pass/fail is unverified** by me. No frontend/e2e/SW/IndexedDB tests exist (F).

---

## 0. Executive summary

1. **The deck and the code are two different products.**
   - Deck (`Munshi_AI_Paytm_Hackathon.pdf/.pptx`): *Munshi AI* — voice-first partner for **kirana** merchants, built on **Paytm** (Soundbox, UPI, payment links, lending), **Cognee** memory graph, **n8n** workflow actions, festive campaigns, smart reorder, khata-photo OCR, loan readiness.
   - Code: *Munim.ai* — voice-first **hardware / building-material shop operating system** (event-sourced ledger, Sarvam Samvaad voice, GST bills, Tally export, offline PWA, vertical pack). Repo folder is `ChhotuAI`.
   - `MunimAI_Investor_Pitch.pptx` is a third artefact: brand "Chhotu.ai", team Aneesh Gupta / Faizan Sheikh, hardware-first. Its speaker notes cite `/Users/faizansheikh/...` paths. **Provenance differs from the hackathon deck (Vatsa Joshi).** Decide which is canonical (§9 Q1).
2. **Overlap is real but partial.** Of the deck's 6 headline features, 1 is present (credit tracker, minus payment links), 1 partial (sales insights), 4 absent. Of the deck's 3 pillars, *Understand* is ~70% present, *Remember* is ~25% (graph-shaped, write-only, no Cognee), *Act* is ~15% (WhatsApp reminders only, no n8n / Paytm).
3. **Engine is strong and reusable**: append-only ledger, idempotent events, FIFO credit, grounded 28-tool agent, per-shop learned aliases, PDF/Tally/import, roles, offline outbox.
4. **Blocking production defects exist** (§7): DB schema never auto-created, default password `admin123` on legacy accounts, unauthenticated tool catalogue, role holes on write endpoints, unescaped-HTML XSS surface, offline mode likely broken on cold start (CDN assets not cached).

---

## 1. Sources compared

| Artefact | What it claims |
|---|---|
| `Munshi_AI_Paytm_Hackathon.pdf` (10 pp) & `.pptx` (10 slides, identical text, no speaker notes) | Munshi AI, Track 1 Merchant Growth AI, kirana persona "Rameshbhai", 3 pillars, 6 features, demo flow, architecture, impact targets, roadmap |
| `MunimAI_Investor_Pitch.pptx` (5 slides) | Chhotu.ai hardware/trade OS; Sarvam stack; roadmap orders→delivery→restock→"Hey Chhotu" |
| `README.md`, `munim-vertical-strategy.md`, `docs/superpowers/**` | Munim.ai capabilities, vertical strategy (hardware→agri→auto→electrical), A/B/C sub-project plans |
| Code | Ground truth for "what exists" |

---

## 2. Technology stack & architecture (F)

| Layer | Implementation |
|---|---|
| Backend | Python 3.10+, FastAPI 0.140.13 (`backend/main.py`, 1944 lines, 62 route handlers + 1 middleware), uvicorn; Vercel entry `app.py`, `maxDuration 60`, daily cron 03:30 UTC (`vercel.json`) |
| DB | PostgreSQL/Neon via psycopg 3, short-lived connections, no pool (`db.py`); 14 tables + legacy `munim_documents`; JSON-file fallback (`repo.py`, `store.py`) |
| Tenancy | `user_id` predicate in every `SqlRepo` query; ContextVar-bound per request; staff map to owner ledger. **No row-level security.** |
| AI | **Sarvam-only**: STT `saaras:v3` (codemix), TTS `bulbul:v3` (default speaker `shubh`), LLM `sarvam-30b` (reasoning, OpenAI-compatible), Document Intelligence for OCR, **Samvaad v6** voice agent (models set in Sarvam console, not repo). Rapidfuzz for matching. No Cognee, no n8n, no other LLM. |
| Voice | Browser SDK bundle (`frontend/assets/samvaad.bundle.js`, 36.9 KB) → signed-URL proxy `/api/voice/samvaad/...` (key never in browser); Samvaad calls `/api/agent/tool/{name}`; fallback record→`/api/transcribe`→`/api/converse` |
| Messaging | Twilio WhatsApp REST (sandbox default), delivery polling 6 s; `MUNIM_TEST_RECIPIENT` redirect |
| Docs | reportlab PDFs (7 types), 7-day token URLs `/d/{token}/{file}` |
| Frontend | One 5,403-line `frontend/index.html` (Tailwind CDN, Chart.js CDN, Google Fonts), `sw.js` (84 lines), manifest; 9 tabs |
| Packs | `verticals/hardware/` — 160 SKUs, ~1,091 aliases, 51 alias priors, GST/HSN map, units, prompt fragment |

### Data flow (voice)
Browser mic → Samvaad session (signed URL) → agent calls `/api/agent/tool/{tool}` with secret + caller/shop_key → `agent.handle` resolves tenant → deterministic tool → `{{facts}}` JSON (≤3000 chars) → agent speaks. `show_bill`/`show_summary` write `voice_presentations` rows the browser polls at 1 Hz (20 s auto-dismiss). Sends are separate tools.

---

## 3. Module map

| Path | Responsibility |
|---|---|
| `backend/main.py` | Routes, middleware, `_write_events`, dashboard, invoice OCR pipeline, bills, staff |
| `backend/agent.py` (1843) | 28-tool registry: 14 read, 9 write, 5 present/send |
| `backend/ledger.py` | Event replay, units, landed cost, margin, reconciliation |
| `backend/crm.py` | Receivables, FIFO allocation, analytics, due list |
| `backend/matcher.py`, `learning.py`, `knowledge_graph.py` | Phrase→SKU, per-shop learning, graph mirror |
| `backend/conversation.py` (1997) | **Legacy** Hinglish dialogue controller (hard-coded demo SKUs) |
| `backend/sarvam_client.py`, `samvaad_*.py` | Sarvam wrapper, Samvaad proxy + generated console config |
| `backend/notify.py`, `whatsapp.py`, `messages.py`, `pdfs.py`, `documents.py`, `presentations.py` | Outbound bills/summaries/reminders, PDFs, tokens |
| `backend/tally_export.py`, `catalogue_import.py`, `hsn.py`, `verticals.py` | Tally XML, bulk import, HSN/e-way, vertical packs |
| `backend/auth.py`, `permissions.py`, `sync.py`, `clock.py`, `db.py`, `sqlrepo.py`, `repo.py`, `store.py`, `migrate.py`, `seed.py` | Auth/roles, offline outbox, time, persistence, migration, demo data |
| `backend/acceptance.py`, `probe_agent.py`, `scenarios_agent.py`, `make_invoice_*.py` | Dev/E2E tooling (`acceptance.py` is stale) |

---

## 4. Gap analysis: deck claim → code reality

Legend: ✅ present · 🟡 partial · ❌ absent.

### 4.1 Three pillars

| Deck pillar / claim | Status | Evidence & gap |
|---|---|---|
| Understand: voice queries in **10+ Indic languages** via Sarvam ASR/TTS | 🟡 | Prompt tells Samvaad to reply in any Sarvam language (`samvaad_config.py:25-29`). Code deterministically handles only Hindi/English/Devanagari (`nlp.py`, `translit.py`, `conversation.py:100`). **UI is hard-coded Hinglish, no i18n; language setting = Auto/Hindi/English.** Landing claims "all Sarvam languages". Investor deck says Samvaad = 11 languages. |
| Understand: photos of bills & khata **digitised by OCR** | 🟡 | Supplier **invoice** OCR works (`sarvam_client.parse_document`, `main.py:1393-1552`, landed cost, review). **Khata/notebook page OCR: absent.** `/api/invoice` silently falls back to a fixture if parse fails (`used_fixture` flag). |
| Remember: per-merchant memory graph (**Cognee**) linking customers, products, suppliers, payments, credit | 🟡/❌ | No Cognee anywhere in code. Own graph: entities term/product/family/unit; edges `alias_for`/`belongs_to`/`uses_unit` only (`knowledge_graph.py`). **Nothing reads it** — matcher uses `aliases_learned`; graph is a write-only mirror. No customer/supplier/payment nodes, no traversal, no query API. |
| Act: **n8n** workflows | ❌ | No n8n. Actions run in-process: WhatsApp bill/summary/reminder via Twilio (`notify.py`). |
| Act: payment-link reminders, **Paytm APIs** | ❌ | No payment link/UPI/QR/Paytm code. Payment enum is `cash`/`credit`; UPI only a free-text note in seed. Bills show no pay-link. |
| Act: supplier reorders | ❌ | `low_stock` alerts only; no reorder qty/supplier; PO PDF exists but nothing generates lines from low stock. |
| Act: festive offers | ❌ | Zero seasonal/festival logic; no offer/campaign object; no customer segmentation send. |
| Act: loan-eligibility nudges / **lending hook** | ❌ | No score, cash-flow export or lender hook. Building blocks exist (outstanding, repeat rate, AOV, margin trend, inventory value). |

### 4.2 Six key features

| # | Deck feature | Status | Detail |
|---|---|---|---|
| 1 | Sales insights: daily **voice briefing**, top sellers, slow movers, **peak hours** | 🟡 | ✅ day/week/month/range summary, `top_items` (top/slow/margin), frozen capital (60 d), spoken `business_summary`, summary PDF to WhatsApp. ❌ **peak hours** (no hour bucketing; `occurred_at` mostly null). ❌ scheduled proactive daily briefing (cron only sends udhaar reminders). 🟡 slow movers exclude zero-sale items (I). |
| 2 | Credit tracker: auto udhaar ledger + **payment-link** reminders | 🟡 | ✅ receivables, FIFO by deadline, per-customer dues, WhatsApp reminders (manual + daily cron, 2 days before). ❌ payment link. Gaps: reminder covers only next due (not total); overpayment dropped; no aging buckets; overdue = negative-days only. |
| 3 | Smart reorder: predicts stock-outs, drafts supplier orders from past bills | 🟡 | ✅ stock-out prediction: `days_left = stock / (sales_30d/30)`, flag ≤7 d or <5 default units (unit-blind) (`main.py:1076-1129`). ❌ reorder qty, supplier model, PO drafting. No supplier entity at all. |
| 4 | Festive campaigns | ❌ | Nothing. |
| 5 | Loan readiness | ❌ | Nothing. |
| 6 | Khata digitiser | ❌ | Nothing for notebook pages (only supplier invoices). |

### 4.3 Demo flow (slide 5): "Is hafte kaun paisa baaki rakh raha hai?" → action in <10 s

| Step | Status |
|---|---|
| 1 Merchant speaks Hindi | ✅ Samvaad voice |
| 2 Sarvam ASR, intent | ✅ (Samvaad agent LLM decides tool) |
| 3 Memory lookup "7 customers, ₹18,400 overdue" | 🟡 `dues` tool (`agent.py:910`) returns open dues within N days incl. overdue; no "this week" window semantic guarantee; sourced from CRM, not graph |
| 4 Hindi voice answer | ✅ |
| 5 One-tap action: n8n sends **Paytm payment links** on WhatsApp | 🟡 `send_reminders` sends WhatsApp text reminders; **no payment link, no n8n, no "one-tap" UI** (reminders are per-customer button or voice) |
| <10 s end-to-end | (I) unmeasured; Vercel timeouts 50-60 s, Sarvam reasoning model latency uncontrolled |

### 4.4 Architecture slide

| Box | Status |
|---|---|
| Input: Voice (Soundbox/app mic) | 🟡 app mic ✅, telephony via caller number ✅ (`probe_agent`), **Soundbox ❌** |
| Input: Images | 🟡 invoices only |
| Input: **Paytm UPI + settlements** transactions | ❌ no transaction ingestion, no reconciliation of UPI receipts to udhaar |
| Sarvam ASR/TTS | ✅ |
| OCR "layout-aware" | 🟡 Sarvam Doc Intelligence, invoice-only |
| Normaliser (entity + amount parsing) | ✅ `nlp.py`, matcher, `agent._number` |
| LLM orchestrator (intent routing, tool calls) | ✅ Samvaad + 28 tools |
| Cognee graph | ❌ (see above) |
| Insight engine: trends, anomalies, **forecasts** | 🟡 30-day margin trend, 8-wk acquisition; **no forecast, no anomaly detection** |
| n8n / Paytm APIs / Lending hook | ❌ ❌ ❌ |

### 4.5 Impact & roadmap
- Impact targets (30% faster recovery, 5 hrs/week, 2× offers) are projections; **no instrumentation exists** (no events for reminder→payment conversion, time saved, or offers). (F: grep)
- Roadmap "Hackathon MVP: voice Q&A, credit tracker, payment-link workflow" → first two done, third not.
- Roadmap M1-2 "pilot 50 merchants Vadodara/Mumbai", M3-4 "OCR khata, reorder engine, festive", M6 "Soundbox, lending, merchant app": none started. Note strategy doc says hardware wholesale launch; deck says kirana — conflicting market.

### 4.6 What code has that the deck does **not** mention (candidates to keep/cut)
Event-sourced ledger with backdating & UNCOUNTED≠0; per-shop learned aliases; frozen-capital; GST invoice/HSN/e-way flag; challan/quotation/proforma/PO; credit/debit notes & returns; Tally XML; bulk import + price tiers; staff roles; thermal receipts (backend only); offline outbox; vertical packs; landed-cost invoice digitisation.

---

## 5. Observed requirements (EARS, condensed; evidence)

### 5.1 Auth, tenancy, roles
- The system shall authenticate by phone+password (PBKDF2-SHA256, 600k iters) and issue 30-day sessions stored only as HMAC hashes, delivered as Bearer token and httponly/lax cookie (Secure only when `VERCEL` set). `auth.py:18,221`, `main.py:213-220`
- When an `/api/*` request outside the open list lacks a valid session, the system shall return 401. `main.py:139-152`
- Open prefixes: `/api/auth/`, `/api/cron/`, `/api/agent/`, `/assets/`, `/d/`, `/data/`. `main.py:127`
- When staff act, the system shall read/write the **owner's** ledger. `main.py:79-85`
- Roles: owner {sale,lookup,write,delete,settings,manage_staff}; manager {sale,lookup,write}; staff {sale,lookup}. Denied → 403. `permissions.py:16-20`
- When onboarding completes, the system shall validate GSTIN, seed the hardware pack, and not fail on pack errors. `main.py:271-300`

### 5.2 Ledger & credit
- Stock shall only be derived from events; no stored stock. UNCOUNTED until an `opening_balance`/`stock_take`. `ledger.py:3-6,133`
- Same-day replay order: opening/stock_take 0, delivery 1, sale 2, sales_return 3, credit/debit note 4, adjustment 5. `ledger.py:25-27`
- credit_note/debit_note shall be stock-neutral; sales_return adds stock. `ledger.py:125-132`
- Insert with existing `(user_id,event_id)` shall be a no-op. `sqlrepo.py:119`, `db.py:80`
- Margin shall use the latest delivery rate on/before the sale date (replacement cost, not FIFO/avg). `ledger.py:164-182`
- Payments shall be allocated to receivables by earliest deadline from a pooled sum; balances are derived. `crm.py:80-105`
- When a payment ≤0 or > outstanding+0.01, the system shall return 400. `main.py:1033`
- A credit sale without a customer shall be refused; default deadline today+30. `agent.py:1163,1183`
- A SKU/customer with history shall not be deletable (409). `main.py:1014,1210`
- When a sale has no rate, the system shall assume landed cost ×1.10 and flag `rate_assumed`. `main.py:912-916`

### 5.3 Voice agent
- Tenant shall be resolved only from exact caller phone or `shop_key`; else refuse. `agent.py:94-112`
- Secret compared constant-time to `SAMVAAD_WEBHOOK_SECRET`. `agent.py:63`
- Unfilled `{{…}}` args shall be discarded. `agent.py:442-457`
- Ambiguous SKU → return names, never guess. `agent.py:257-326`
- Duplicate write with same `request_id` within 8 s → `duplicate:true`. `agent.py:1015-1068`
- Agent shall send exactly the previewed bill (`presentation_id`); shall not claim a write unless tool returned recorded. `agent.py:1466`, `samvaad_config.py:176`
- Matcher stages: exact id → unique substring → alias index (+fuzzy learned) → vertical prior (conf 0.9) → attribute→family → rapidfuzz ≥0.6 (auto ≥0.92 & 0.15 lead) → sarvam-30b rerank → confirm top-3. Gates: live_sale .80, delivery/count/stock_take .92, recall .88. `matcher.py:26,326`
- Unstocked attribute value (e.g. Fe550) → `not_stocked`, never substitute. `matcher.py:255`
- Confirmed matches shall strengthen aliases/unit/attribute priors and mirror to the graph (non-blocking). `learning.py:148-191`

### 5.4 Documents, messaging, exports
- Bill shall recompute amounts and GST from the catalogue; CGST=SGST=GST/2 (no IGST). `notify.py:39-56`, `pdfs.py:210`
- Bills >₹50,000 shall show e-way reminder or number (display only, no portal). `hsn.py:54`
- Documents: tax invoice, challan (no prices), quotation, proforma, PO, thermal 58/80 mm, summary. `pdfs.py`
- Generated PDFs are served by 32-byte token URL, TTL 7 days. `documents.py:17`
- When `MUNIM_TEST_RECIPIENT` set, all WhatsApp sends shall be redirected + prefixed. `whatsapp.py:52-77`
- Reminder delivery status polled ≤6 s; success only on delivered/read/sent. `whatsapp.py:140`
- Cron `/api/cron/reminders` sends due reminders (≤2 days incl. overdue) for every onboarded user; 503 if no secret, 403 if wrong. `main.py:366-394`
- Tally XML: Sales, Purchase, Credit Note (returns+credit notes), Debit Note, Receipt vouchers. `tally_export.py`
- Import shall preview (no writes) then commit; match by sku_id then case-insensitive name. `catalogue_import.py:104-149`

### 5.5 Offline & sync
- Outbox events shall carry client ULID; server returns `accepted|duplicate|rejected|conflict_superseded` and stamps per-tenant `seq`. `sync.py:181-210`
- product_edit is last-write-wins (arrival order) with audit row; stock_take conflicts resolved by `occurred_at` string compare. `sync.py:81-124`
- Snapshot returns stock + dues (no JS port of replay). `sync.py:240`
- Frontend: SW caches `/` and manifest; network-first cache for GET `/api/stock|customers|sync/snapshot|state`; IndexedDB `munim_outbox`; offline banner + typed quick-entry for `sale` only. `sw.js`, `index.html:5162-5400`

### 5.6 Vertical pack
- Pack shall be rejected on missing gst_rate, unknown unit, cross-family alias collision, bad alias_prior ref, or version ≠ meta. `verticals.py:61-124`
- Only `hardware` exists (160 SKUs, all 18% GST, 8 families).

---

## 6. Target spec — closing the deck gap

**Scope decision assumed** (change if Q1 says otherwise): keep Munim.ai as the engine; add a **"Merchant Growth" layer** implementing the deck's promises for kirana/general merchants, sharing the ledger. New work is additive, appended DDL, no changes to frozen ledger contract (`_TYPE_ORDER`).

Priority: **P0** = required for deck's demo flow; **P1** = deck features; **P2** = deck roadmap/scale.

### 6.1 P0 — Demo-flow completion

**FR-1 Payment links on reminders** (deck: "Paytm payment links on WhatsApp")
- Where a payment-link provider is configured, when a reminder is sent, the system shall include a link for the customer's outstanding amount.
- Provider adapter interface with one implementation (Paytm Payment Links API if credentials/sandbox available; else UPI deep-link `upi://pay?...` + QR on bill PDF as a fallback). Config: `PAYTM_MID`, `PAYTM_KEY`, `PAYMENT_LINK_PROVIDER`.
- Payment enum extended: `cash|credit|upi`. Paid webhook creates an immutable `payments` row (idempotent by provider txn id).
- *Acceptance*: reminder to a test customer contains link; simulated webhook reduces outstanding FIFO; replayed webhook is a no-op; provider outage falls back to text reminder and says so.

**FR-2 One-tap "collect all overdue"** (deck step 5)
- When owner asks "kaun paisa baaki rakh raha hai", the agent shall return count + total overdue (+ top N names) and offer send; on confirmation, send one reminder per customer with phone, each with FR-1 link, skipping customers reminded in last 24 h; report sent/failed counts.
- New tool `dues_overdue(period)` (explicit "this week" window: deadline ≤ today) and reuse `send_reminders`. UI: single "Send all reminders" button on Customers tab with preview list.
- Reminder amount shall be **total outstanding**, not just next due (fixes `notify.py:139`).
- *Acceptance*: with 7 seeded overdue customers totalling ₹18,400 the tool returns 7 / 18400; send produces 7 delivery records; second tap within 24 h sends 0.

**FR-3 Latency budget**: voice question→spoken answer p95 ≤ 10 s for read tools (deck claim). Instrument tool time + Samvaad round trip; expose in `/api/health`-adjacent metrics.

### 6.2 P1 — Deck features

**FR-4 Daily voice briefing (insights)**
- Cron (per-shop local time, default 9:00) shall build a briefing: yesterday sales/margin, top 3, slow 3, overdue total, low-stock count, **peak hours**; deliver as WhatsApp text/PDF and available by voice (`daily_briefing` tool).
- Peak hours requires `occurred_at` hour on sale events: capture on every write path (`_write_events`, agent `_commit`, sync) and aggregate in shop TZ; when <20 timed sales exist, omit and say "not enough data".
- *Acceptance*: briefing includes hour-of-day histogram from 30 days; missing timestamps excluded, not zero-filled.

**FR-5 Smart reorder**
- Add `reorder_level`, `lead_time_days`, `supplier_id` per SKU; supplier entity (name, phone) + supplier ledger link to `delivery` events.
- Suggestion = `max(0, velocity_30d × (lead_time + cover_days) − stock)` in the SKU's default unit; unit-aware (fix unit-blind <5 floor).
- Tool `reorder_suggestions`; on confirm, generate PO PDF (existing `purchase_order_pdf`) and WhatsApp it to supplier (uses test-recipient redirect).
- *Acceptance*: seeded SKU with 10 units/day and 3 days stock and 5-day lead time suggests ≥ 40 units; UNCOUNTED SKUs excluded with explicit note.

**FR-6 Khata digitiser**
- New endpoint + UI: upload photo/PDF of a notebook page → Sarvam Document Intelligence → LLM extraction of rows `{customer, amount, direction(udhaar|jama), date}` → **review screen** → commit creating customers, receivables and payments (idempotent by `evidence.source_hash`+row).
- Never auto-commit; uncertain rows held. Handwritten reliability is (I) unproven — require a 20-page field sample before claiming accuracy.
- *Acceptance*: fixture page with 10 rows yields ≥8 correct after review; nothing written before confirm; re-upload of same image writes 0 new rows.

**FR-7 Festive campaigns**
- Festival calendar table (Navratri, Diwali, Eid, Holi, Raksha Bandhan, Ganesh Chaturthi… by year, region-tag) shipped as data.
- 14 days before a festival: suggest offer per shop from last-year sales of the same window (or top-margin items if no history), owner approves, system sends WhatsApp offer to opted-in repeat customers (≥2 orders). Store `campaigns` and per-send outcomes; count redemptions by sale within 7 days.
- Consent: only customers with `whatsapp_opt_in`; production requires approved Twilio templates (currently free-form only — see NFR-5).
- *Acceptance*: campaign dry-run lists recipients and message; nothing sent until approved; outcome report shows sends/replies/sales.

**FR-8 Loan readiness**
- Compute a cash-flow snapshot (12-mo revenue trend, margin, receivable ageing, repeat rate, inventory value, frozen capital) and a plain-language explanation in the owner's language. **No credit decision is made**; output is labelled "indicative". Lending hook = export payload + owner-consented share to configured lender endpoint (mock adapter for hackathon).
- *Acceptance*: explanation generated from deterministic numbers only (LLM narrates, never computes); consent recorded before any share.

**FR-9 Credit ageing & overdue**
- Buckets 0-30/31-60/61-90/90+, per customer and total; overdue flag and days; included in briefing and dues tool.

**FR-10 Memory graph made real** (deck "Remember")
- Decide: (a) integrate Cognee (add dependency, ingest ledger facts as nodes/edges: customer, product, supplier, payment, receivable; tenant-scoped), or (b) extend existing graph and add read paths. Recommendation: **(b) first** — extend `knowledge_graph.py` with customer/supplier/payment edges, add a graph read API and use strong `alias_for` edges as matcher candidates; add Cognee only if the deck's named-stack claim is mandatory for judging.
- Any option: queries like "kis customer ne last month sabse zyada kharida" answered via graph or ledger with evidence.

### 6.3 P2 — Scale / roadmap
- **FR-11 Paytm/Soundbox integration**: ingest UPI settlement feed, auto-reconcile to receivables by customer VPA/phone; Soundbox announcement hooks. Depends on Paytm partner access — mock adapter until then.
- **FR-12 n8n**: expose actions as webhooks (`/api/automation/{action}`) with signed payloads so n8n can orchestrate; keep core actions in-process. Only if judging requires n8n.
- **FR-13 True multilingual**: externalise UI strings (i18n JSON), add languages beyond Hi/En (Gujarati, Marathi first per deck), UI language chooser; deterministic number/unit parsing for Gujarati/Marathi or rely on LLM with tool-side validation.
- **FR-14 Pilot instrumentation**: log reminder→payment conversion, recovery days, time saved proxies, offers launched; dashboard for the 30% / 5 hrs / 2× targets.
- **FR-15 Barcode / staff scan** (strategy Phase 4), weighted-average costing (Phase 5).

---

## 7. Defect & debt backlog (from code, prioritised)

### P0 — fix before any pilot
| ID | Issue | Evidence |
|---|---|---|
| D1 | App never calls `init_schema()`; fresh DB fails until `migrate.py` run | `db.py`, only `migrate.py:48` |
| D2 | Legacy password-less accounts get password `admin123` | `auth.py:20,82-93` |
| D3 | Signup has no OTP/phone verification; anyone can register any number; login/signup distinguish existing accounts (enumeration); no rate limits/lockout anywhere | `auth.py:55-61,136`, `main.py:223-250` |
| D4 | `/api/agent/tools` unauthenticated; agent secret accepted in URL query; failed agent auth returns HTTP 200 | `main.py:568,529-533,400-421` |
| D5 | Missing role checks: `/api/commit` (any type incl. opening_balance/stock_take), `/api/invoice/commit`, `/api/sync/outbox` (staff can rewrite catalogue via product_edit, create SKUs), `/api/onboarding`, tally export, documents, config GET | `main.py:875,1552,1135,271,1799,1841` |
| D6 | Stored-XSS surface: customer/product names & OCR text inserted unescaped in many templates; inline `onclick` string interpolation; token also in localStorage | `index.html:3870,4209,4377,…` |
| D7 | Sync silently drops events for unknown `sku_id` but reports `accepted`; `seq` racy, no unique index, online events get no seq; no per-event try/except | `main.py:906`, `sync.py:202-210` |
| D8 | Content-Disposition built from user-supplied `bill_no/challan_no` unescaped (header injection) | `main.py:1675,1861,1813` |
| D9 | Request bodies are raw dicts: missing `type`/`qty` → 500; no upload size limits (transcribe/invoice/import) | `main.py:875`, various |

### P1 — correctness
| ID | Issue |
|---|---|
| D10 | Tally export ignores unit conversion → wrong amounts when unit ≠ base (`tally_export.py:43-47`); no GST/tax ledgers, no party master |
| D11 | Margin ignores returns/credit notes (`ledger.py:188`) |
| D12 | Catalogue import drops `selling_rate`; update path may overwrite whole SKU (`catalogue_import.py:81-123`) |
| D13 | `notify.send_bill` rows carry no HSN; bill numbers non-unique/non-sequential (`notify.py:54-57`); no IGST/customer GSTIN |
| D14 | FIFO drops overpayments; payments not linked to invoices (`crm.py:80-98`) |
| D15 | Reminders use only next due (`notify.py:139`) |
| D16 | Low-stock floor "<5" unit-blind (`main.py:1094`) |
| D17 | Dashboard steel-rise marker hard-codes `TMT_12_FE500D_TATA` (`main.py:1309`) |
| D18 | `/api/invoice` returns fixture as if real on parse failure |
| D19 | Helvetica cannot render Devanagari in PDFs (names/shop) |
| D20 | `GET /api/state` performs writes (graph backfill); every request loads all events; no DB pool → O(n) scaling |
| D21 | Middleware swallows all auth exceptions → DB outage reads as 401 |
| D22 | Payment race (outstanding check then insert not atomic) |
| D23 | `receivables.status` never updated; expired sessions/documents/presentations not purged (only docs opportunistic) |

### P2 — offline/PWA & UI
| ID | Issue |
|---|---|
| D24 | SW shell caches only `/` and manifest; Tailwind/Chart.js/fonts (CDN) and `samvaad.bundle.js` never cached → cold offline start broken; `/api/me` uncached → lands on login; error responses cached; cache not cleared on logout (cross-user leak on shared device) |
| D25 | Offline: only `sale` quick-entry, no customer for credit; no local delta on stock/dues; no fallback on Samvaad failure; no per-tab offline states; rejected events stay queued silently |
| D26 | Thermal print, staff/roles, e-way bill number, reconciliations have **backend but no UI**; `ROLE` only set at page-load, not after login; onboarding vertical selector is a static label |
| D27 | `/api/bill` fetched without auth header; several handlers lack try/catch; dead legacy voice path (`parseVoice`, `micRecord`, `countPanel`, `cacheFillers`) |
| D28 | Accessibility: no aria-live on toast/conversation, no focus trap, unlabeled inputs, 8 tabs in 6-col mobile bar, icon-only buttons unlabeled, 9-10 px text |
| D29 | `conversation.py` (2k lines) legacy controller hard-codes demo SKUs/GST/messages; stale tool counts (22/23/27 vs actual 28); `samvaad-tool-audit.md` tests v4 vs pinned v6; `acceptance.py` calls removed `/api/reset` |
| D30 | Repo hygiene: real-looking phone number default in `probe_agent.py:41`; Sarvam ids hard-coded; `DEBUG_SAVE_RESPONSES` writes transcripts to `./debug` by default locally; `data/` PII-style demo files in repo and `/data/` route open |
| D31 | `REVIEW.md` may be stale vs fix commit `6e2a790` (structural steel rebrand) — reconcile; human SKU sign-off status unknown |

---

## 8. Non-functional requirements (target)

- **NFR-1 Security**: rate-limit auth/agent/cron; OTP phone verification; escape all rendered strings (central `esc()`); CSP header; remove `admin123`; secrets never in URLs; RBAC test per endpoint.
- **NFR-2 Reliability**: auto-run idempotent schema init on startup; DB pool; atomic seq via `SELECT … FOR UPDATE`/sequence; all writes idempotent by client/request id.
- **NFR-3 Performance**: read tools p95 ≤ 3 s server-side; avoid full-event replay per request (snapshot cache); Vercel 60 s cap respected.
- **NFR-4 Privacy**: tenant isolation tests incl. Postgres (RLS optional); PII redaction in logs; retention for transcripts/debug.
- **NFR-5 Messaging compliance**: approved WhatsApp templates + opt-in tracking for anything outbound to customers (reminders, campaigns) before removing test-recipient redirect.
- **NFR-6 Testability**: keep suite DB-free; add frontend smoke (Playwright) for auth, voice fallback, offline queue; SW tests.
- **NFR-7 Accessibility**: WCAG 2.1 AA for core flows.
- **NFR-8 Observability**: request IDs, tool timing, Sarvam/Twilio error counters, conversion metrics (FR-14).

---

## 9. Open questions / uncertainties

1. **Which product is canonical?** Munshi AI (kirana, Paytm, Vatsa Joshi) vs Munim.ai/Chhotu.ai (hardware, Aneesh/Faizan per investor deck). Strategy doc explicitly ranks kirana B2C *low* (score 22) and says barcode beats voice there; the hackathon deck targets kirana. Recommendation: hackathon submission = Munshi framing on the shared engine; keep hardware pack as the second vertical; add a `kirana` vertical pack (needs SKU seed: atta, dal, oil, biscuits…).
2. Is Cognee/n8n usage **mandatory** for the hackathon track? If yes, FR-10(a)/FR-12 move to P0.
3. Paytm API/sandbox access available? Without it FR-1/FR-11 ship as UPI-link + mock adapter.
4. Are the deck's numbers (7 customers, ₹18,400, 400+ txns, 30 credit customers, 6 suppliers) meant to be **demo seed data**? `seed.py` currently generates hardware data (7 SKUs, 6 customers).
5. Twilio: sandbox only; production sender/templates status unknown.
6. Ambient-noise ASR error rate (strategy Phase 0) remains unmeasured; Sarvam credits reportedly nearly exhausted (design doc §8).
7. Not verified by me: whether `main.py` consumes `reports.yaml` (analyst found no use; `gst_summary` dashboard appears declared-only); whether `repo.upsert_sku` replaces vs merges on import update; full test suite result; `docs/samvaad-setup.md` beyond a skim; `samvaad.bundle.js` contents (minified).
8. Whether `Munshi_AI_Paytm_Hackathon.pptx` has embedded images/notes carrying extra requirements: text extracted only; no speaker notes present.

---

## 10. Suggested delivery order

1. **Stabilise (1 wk)**: D1-D9, D24 (cache CDN assets + `/api/me`), run/repair test suite, reconcile docs (tool counts, REVIEW.md).
2. **Demo flow (1 wk)**: FR-1 (UPI-link fallback first), FR-2, FR-3 instrumentation, kirana seed (Q4).
3. **Deck features (2-3 wks)**: FR-4 briefing+peak hours, FR-9 ageing, FR-5 reorder, FR-6 khata OCR (with field sample), FR-7 festive, FR-8 loan readiness.
4. **Depth (as needed)**: FR-10 graph reads, FR-13 i18n, FR-12 n8n, FR-11 Paytm live, FR-14 pilot metrics.
5. **Strategy carry-over**: UI for thermal print/staff/e-way (D26), barcode, weighted-average costing.
