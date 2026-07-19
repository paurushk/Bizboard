# Bizboard Backend (MVP)

Django + Django REST Framework API for the Bizboard GST billing platform.
Implements the locked MVP from `MVP_IMPLEMENTATION_PLAN.md`: Purchase, Sales,
Inventory, Dashboard/Reports — with dynamic Ledger Service (no stored ledger
tables), typed append-only stock movements, payment allocation, and async PDF.

## Stack

- Python 3.12+, Django 5, DRF, SimpleJWT
- PostgreSQL in production (`DATABASE_URL`); **SQLite fallback** for local/test
- Redis + Celery (eager mode by default for local/dev)
- OpenAPI via drf-spectacular at `/api/v1/docs/`

## Quick start (local)

```bash
cd backend
python -m venv .venv

# Windows
.\.venv\Scripts\activate
# macOS / Linux
# source .venv/bin/activate

pip install -r requirements-dev.txt
copy .env.example .env   # or: cp .env.example .env

python manage.py migrate
python manage.py runserver
```

API root: `http://127.0.0.1:8000/api/v1/`  
Swagger UI: `http://127.0.0.1:8000/api/v1/docs/`  
Health: `http://127.0.0.1:8000/api/v1/health/`

### Register a company + owner

```http
POST /api/v1/auth/register/
{
  "company_name": "My Shop",
  "email": "owner@example.com",
  "password": "StrongPass123!",
  "state": "Karnataka"
}
```

Returns JWT `access` / `refresh` tokens. Use `Authorization: Bearer <access>`.

## Environment

| Variable | Purpose |
|---|---|
| `DJANGO_SECRET_KEY` | Django secret |
| `DJANGO_DEBUG` | `1` / `0` |
| `DATABASE_URL` | PostgreSQL URL; **omit for SQLite** |
| `REDIS_URL` | Celery broker |
| `CELERY_TASK_ALWAYS_EAGER` | `1` runs tasks in-process (default local) |
| `CORS_ALLOWED_ORIGINS` | Frontend origins |

See `.env.example`.

## API surface (`/api/v1/...`)

| Prefix | Module |
|---|---|
| `/auth/` | Register, login, refresh, logout, OTP, me |
| `/company/` | Profile, GST settings, users |
| `/customers/` `/suppliers/` `/products/` | Masters |
| `/masters/...` | Categories, brands, units, tax rates |
| `/purchases/` | Invoices + returns (Draft → Complete → Cancel) |
| `/sales/` | Invoices, quotations, returns + PDF/share |
| `/payments/receipts/` `/supplier-payments/` `/allocations/` | Payments |
| `/inventory/` | Balances, movements, adjustments, alerts |
| `/ledgers/customers/` `/ledgers/suppliers/` | Dynamic ledgers |
| `/dashboard/` `/reports/` `/exports/` | Report Service |
| `/search/` | Universal search |
| `/imports/` | Upload → preview → commit |
| `/files/` `/notifications/` `/audit/` | Supporting services |

## Architecture notes

- **Service layer** — document modules call services; views stay thin.
- **Domain events** — in-process bus (`core.events`); no broker in MVP.
- **Ledger Service** — customer/supplier statements derived from documents +
  allocations. **No `customer_ledgers` / `supplier_ledgers` tables.**
- **Stock** — append-only `stock_movements` with typed `movement_type`;
  `stock_balances` is a rebuildable cache (`on_hand`, `reserved=0`, `available`).
- **Document numbers** — assigned on Complete via `DocumentNumberService`
  (row-locked sequences).
- **Async PDF** — Complete returns immediately; Celery renders A4 PDF.

## Tests

```bash
pytest
# or
python -m pytest -q
```

Coverage includes tax calc, stock flow, status machines, business rules,
tenant isolation, payment allocation, ledger math, imports, and PDF.

## Docker

From the monorepo root (with `docker-compose.yml`):

```bash
docker compose up --build api worker
```

The `api` service builds from this directory (`./backend`).

## Celery worker (non-eager)

```bash
# set CELERY_TASK_ALWAYS_EAGER=0 and REDIS_URL
celery -A config worker -l info
```
