# Bizboard

Cloud-first GST billing and business management for Indian retailers, small
traders, and small wholesalers.

## MVP

- GST and non-GST sales invoices, quotations, and returns
- Purchases and purchase returns
- Barcode/SKU/name product lookup
- Append-only inventory movements and stock balances
- Customer receipts, supplier payments, and invoice allocations
- Dynamic customer and supplier ledgers
- Dashboard, reports, PDF/A4 invoices, imports, and exports
- Owner/Admin and Sales Staff roles in a shared-database tenant model

The approved scope and acceptance criteria are in
[`MVP_IMPLEMENTATION_PLAN.md`](MVP_IMPLEMENTATION_PLAN.md).

**Phase 0 (pilot hardening):** canonical DoD
[`docs/pilot/PHASE_0_DOD.md`](docs/pilot/PHASE_0_DOD.md),
implementation plan
[`docs/pilot/PHASE_0_IMPLEMENTATION_PLAN.md`](docs/pilot/PHASE_0_IMPLEMENTATION_PLAN.md).

## Local development

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

Optional mock UI without API: set `VITE_USE_MOCKS=true` in `web/.env`.

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

## Verification

```sh
cd backend && pytest
cd web && npm run lint && npm test -- --run && npm run build
docker compose config
```

GST calculations and invoice layouts require CA approval before a production
pilot.
