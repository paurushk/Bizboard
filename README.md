# Bizboard

Cloud-first GST billing and business management for Indian retailers, small
traders, and small wholesalers.

## MVP

Pilot-honest scope for Indian retailers and small traders:

- GST and non-GST sales invoices, quotations, and returns
- Purchases and purchase returns (no separate GRN — purchase Complete posts stock and AP together)
- Barcode/SKU/name product lookup
- Append-only inventory movements and stock balances
- Customer receipts, supplier payments, and invoice allocations
- Dynamic customer and supplier ledgers
- Dashboard, core reports, PDF/A4 invoices, imports, and exports
- Owner/Admin and Sales Staff roles in a shared-database tenant model

**Feature-flagged (off by default in production pilots):** GSTR report
screens, e-invoice sandbox submit, accounting modules, AI insights, and
Tally migration. Enable via `VITE_ENABLE_*` / `VITE_PILOT_ADVANCED` for
local demos — see `web/.env.example`.

**Not claimed in this pilot:** live NIC e-invoice / GST portal filing
(sandbox submit is preview only), GSTR-2B ITC match, WhatsApp beyond share-link,
native mobile, Postgres RLS, full perpetual FIFO COGS, Manufacturing,
Payroll, CRM, multi-company / multi-branch GSTIN, or live bidirectional Tally sync.

The approved scope and acceptance criteria are in
[`MVP_IMPLEMENTATION_PLAN.md`](MVP_IMPLEMENTATION_PLAN.md).

**Phase 0 (pilot hardening):** canonical DoD
[`docs/pilot/PHASE_0_DOD.md`](docs/pilot/PHASE_0_DOD.md),
implementation plan
[`docs/pilot/PHASE_0_IMPLEMENTATION_PLAN.md`](docs/pilot/PHASE_0_IMPLEMENTATION_PLAN.md),
Wave 0 audit [`docs/pilot/WAVE0_AUDIT.md`](docs/pilot/WAVE0_AUDIT.md),
go/no-go [`docs/pilot/GO_NO_GO.md`](docs/pilot/GO_NO_GO.md).
Pilot fixtures: `python manage.py seed_pilot_fixtures`.


## First-run onboarding

Self-serve path: Register then Login, then guided /setup when ENABLE_SETUP_WIZARD=1 and VITE_ENABLE_SETUP_WIZARD=true. When off, Owners see the dashboard checklist only. See docs/onboarding/NEW_USER_ONBOARDING_PLAN.md.

## Local development

Optional (M1-034): enable the repo's git hooks — currently just a guard against
accidentally committing a populated `.env` at the repo root:

```sh
git config core.hooksPath .githooks
```

### Docker (recommended)

1. Copy `.env.example` to `.env` and replace development secrets.
2. Start the stack:

   ```sh
   docker compose up --build
   ```

3. Open `http://localhost`. API docs: `/api/v1/docs/`.

### Without Docker

Backend:

```sh
cd backend
python -m venv .venv
# Module-invocation form (BUG-734) is more robust to PATH ambiguity on
# machines with multiple Python installs than a bare `pip install`.
.venv/Scripts/python -m pip install -r requirements-dev.txt
.venv/Scripts/python manage.py migrate
.venv/Scripts/python manage.py seed_demo
.venv/Scripts/python manage.py runserver
```

Frontend (separate terminal):

```sh
cd web
npm install
npm run dev
```

Optional mock UI without API: set `VITE_USE_MOCKS=true` in `web/.env`
(local/e2e only — production builds refuse this flag).

SQLite is used when `DATABASE_URL` is absent. PostgreSQL is required for
production.

### Demo credentials (after seed_demo)

| Field | Value |
|---|---|
| Email | `demo@bizboard.local` |
| Password | `DemoPass123!` |

## Architecture invariants

- Completed business documents are the source of truth.
- There are no customer or supplier ledger tables.
- Ledger balances are derived from documents, returns, and payment allocations.
- Stock movements are typed and append-only.
- Document completion and inventory effects are atomic.
- Every business query is scoped to `company_id`.
- Public APIs are versioned under `/api/v1/`.
- Advanced surfaces (GSTR, AI, Tally, e-invoice submit, accounting) are
  gated by frontend feature flags and must not be presented as live GSTN
  filing in pilot materials.

## Verification

```sh
cd backend && pytest
cd web && npm run lint && npm test -- --run && npm run build
docker compose config
```

GST calculations and invoice layouts require CA approval before a production
pilot.

## Wave 17–21 honesty (authoritative)

| Module | Honest status |
|--------|----------------|
| Billing + inventory + receipts/payments | Pilot core |
| Accounting books | Optional dual-ledger; cess GL + period gates in remediation |
| GSTR-1/3B aids | Offline worksheets — not GSTN filing |
| e-Invoice / e-Way | Sandbox/preview only — live NIC deferred |
| Manufacturing / Payroll / CRM | **Dark in production** unless `ENABLE_*` + company `feature_flags` |
| WhatsApp Cloud / AA banking | **Dark** unless flagged; no mock ingest in prod |
| Capacitor / native stores | **Not a store app** — Android WebView shell for Play internal testing; no App Store/iOS binary |
| PWA / offline install | **Service worker + offline.html** — shell precache; `/api` not cached; IDB outbox for drafts; no iOS background-sync guarantee |
| Tally | Export dump / optional HTTP — not live bidirectional sync |
| RLS | Off by default (`POSTGRES_RLS_ENABLED=0`) until proven |

Do not cite Wave 17/18 “MVP-complete” scores as launch gates. See `docs/reviews/KNOWN_LIMITATIONS_AND_TECH_DEBT.md`.

## Wave 18 — POS & billing UX

- **POS (`/pos`)** — feature-flagged counter checkout (`VITE_ENABLE_POS` / `ENABLE_POS`). Creates a retail invoice, completes it, records cash/UPI receipt, and downloads thermal PDF when available. MVP only — not a full retail suite.
- **Offline draft outbox** — Invoice editor and POS share a v2 outbox (`web/src/offline/invoiceDraftCache.ts`): IndexedDB primary with localStorage fallback, flushed with the same idempotency key when back online. Drafts are **plaintext on device** (sign-out wipes). **PWA service worker** (`vite-plugin-pwa`) precaches the app shell and serves `/offline.html` for failed navigations; authenticated `/api` responses are not Workbox-cached. Sign-out / session-expired purge `bizboard-api` and `bizboard-pages` caches. Not a full offline ERP — install is installable shell + draft outbox, not offline install of the whole product.
- **New Invoice shortcuts** — `Ctrl/Cmd+S` save draft, `Ctrl/Cmd+Enter` save & complete (when available), `Ctrl/Cmd+Shift+L` focus product search, `F2` scan barcode.

## Wave 18 honesty

POS, offline draft outbox, cess, GSTR-1 DOC/AT, ERP FE CRUD, PWA (service worker + offline.html), and Hindi expansion are **MVP-complete for billing dogfood**. Not Zoho/TallyPrime/ERPNext full parity (BB-000591). Manufacturing/payroll/CRM remain preview/dark. Final Gates remain ops-only.

## Wave 19 honesty

Wave 19 closed remaining code residuals (SO/DC/PO cess, invoice IndexedDB/localStorage outbox, statutory events UI, typed domain OpenAPI clients, RLS table+Celery GUC coverage with flag still off by default, resources.ts split + real virtualization, GSTR-9 table 18 + AT depth). Final Gates remain ops-only.
