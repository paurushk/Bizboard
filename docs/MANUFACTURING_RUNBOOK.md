# Manufacturing runbook

For whoever switches Manufacturing on for a company, trains a factory on it, or has to back it out.
What was built and how it was verified is in [MANUFACTURING_IMPLEMENTATION_PLAN.md](MANUFACTURING_IMPLEMENTATION_PLAN.md), section 12.

## 1. What is switched on, and by what

| Part | Switch | Who may use it |
|---|---|---|
| Recipes, work orders, quick production, reports, print sheets | `ENABLE_MANUFACTURING` (a dark module: the plan, or the company grant `manufacturing_pack_grant`) | owner, manager, inventory staff post; accountant and auditor read and see costs |
| Planning (shortages, what to buy and make, load, can-I-promise) | `MFG_PLANNING` | same |
| Quality (inspections, holds, quality problems, scorecard) | `MFG_QUALITY` | same |
| Job work and ITC-04 | `MFG_JOB_WORK` | same |
| Costing in the books (work in progress, absorption, variance journals, standard-cost re-pricing) | `MFG_COSTING_GL` | same; **off until the CA has signed (QOS-0141)** |
| Shop floor (job cards, stoppages, machines, operators, the tablet) | `MFG_SHOP_FLOOR` | same |

The sub-switches are ordinary rollout flags:

```bash
python manage.py grant_rollout_flag --email owner@example.com --flag MFG_PLANNING
```

The module itself is granted with `manufacturing_pack_grant` on the company's feature flags (the same grant
`enable_full_demo --with-manufacturing-pack` writes). A new company is on the pack sidebar, which hides Manufacturing; take
`NAV_PACK_DEFAULT` off the company to show it.

Existing companies keep the old one-step work order (material is taken and output recorded together) until the owner
changes **Manufacturing settings > New work orders** to "Issue, return and output as separate steps". Orders already created keep
the way they were made.

## 2. Demo and training

```bash
python manage.py seed_manufacturing_demo --email owner@example.com           # recipes, work centre, operator DEMO1 (PIN 2468)
python manage.py simulate_manufacturing_month --email owner@example.com --days 30   # a month of activity, checked every day
```

Both refuse on staging and production. The simulation exits non-zero on the first day an invariant breaks.

## 3. Work done outside, extra material, re-pricing, labels

- **A step done by a job worker.** A routing step marked "done outside" gets a **Send to job worker** button on its job card
  (Shop floor > Job cards, and the work order's Floor tab). It raises the job-work order and challan with the material that
  goes out (the material the order still has to take, which can be edited). Issuing the challan starts the step; the work order
  cannot be completed or cancelled while a step is still out. When the job worker returns the goods, record the receipt on the
  Job work screen: the step shows the quantity back and the job worker's charge, and, if the returned item is one of the
  work order's materials, a draft issue is made so it goes into the order; any other returned item gets a draft marked as extra material, which a manager approves. The charge is in the cost of the returned goods
  already, so the order is not charged twice. Closing an empty job-work order puts the step back to waiting. Needs `MFG_JOB_WORK`
  and `MFG_SHOP_FLOOR`.
- **Extra material.** A floor user who tries to issue more than the order needs (beyond the allowed percentage) keeps the draft and
  can **Ask a manager to approve**. A manager sees "Waiting for a manager" on the work order's Material tab and either
  approves (which posts the issue) or turns it down with a reason; the draft stays and can be asked about again.
- **Re-pricing stock to a new standard cost.** Reports > Standard costs > *Re-price stock to the standard cost*. Preview lists
  every lot that would change; nothing moves until **Post**. Posting takes each lot out and back in through the stock ledger at
  the standard, so running cost and FIFO layers agree, and one journal moves the difference between Inventory (1400) and
  Manufacturing Variance (5420). A run can be reversed as a whole, and only while none of its lots has moved since. Items tracked by
  serial number are left out. Needs `MFG_COSTING_GL`, so it waits for the same CA sign-off (QOS-0141).
- **Batch label and work order list.** A posted production receipt has **Print batch label** (item, batch, quantity, dates, work
  order; no money). The work order list has **Download as CSV** (costs only for roles that may see costs).

## 3a. The shop-floor tablet

- Operators are created in **Shop floor > Operators** with a code and a 4 to 8 digit PIN. They have no Bizboard account.
- The tablet address is on **Manufacturing settings** (`/floor?company=<id>`). It signs the operator in, polls every 20 seconds
  and signs out when the token ends.
- With no signal the tablet keeps what the operator taps, with the time of each tap, and sends it in order when the connection is
  back (or when the operator presses **Send now**). Each tap carries a key, so a resend is never applied twice. A tap older than
  a day or in the future is not believed and the server's clock is used. Taps stay on the tablet for the operator who made them.
- Five wrong PINs lock that operator for 15 minutes. Turn an operator off from the same screen when someone leaves.
- The tablet routes need no login, so they name the company for row-level security themselves; they were checked live as a
  non-superuser database role.

## 4. Deploying

1. Migrations, in order: `masters 0034`, `inventory 0033`, `quality 0001`, `manufacturing 0011-0015`, `jobwork 0001-0002`,
   `core 0064-0065` (row-level security for every new table). `0012` is a data migration (recipe version numbers, work order fields,
   consumed serial numbers); it is safe to run twice. Run it on a copy of real data first (QOS-0145).
2. The new tables are in tenant backup, restore and wipe (`accounts/mfg_backup.py`).
3. Regenerate nothing by hand: `docs/openapi-snapshot.json` and `web/src/api/openapi-types.ts` are generated.
4. Attention rows (`WO_LATE`, `WO_SHORTAGE`, `WIP_STALE`, `BATCH_ON_HOLD`, `NCR_OVERDUE`, `JOBWORK_AGEING`, `ITC04_DUE`, and `WO_APPROVAL_WAITING` for an extra-material request nobody has decided) appear
   for companies with the matching switch on; no setting is needed.

## 5. Before a real company switches a part on

- **Costing in the books:** CA sign-off on QOS-0141. The journals it writes are listed in plan section 3.3.
- **Job work and ITC-04:** CA review on QOS-0142. The screen prepares the tables; it does not file.
- **Hindi:** the strings were written by the engineers; QOS-0143 asks a native speaker to read them.
- **Tablet:** try it on a real device (QOS-0144).

## 6. Backing out

Switch the flags off. Nothing is deleted: recipes, orders, documents and journals stay, and the screens and endpoints for a
switched-off part answer "not found". A work order already in separate-steps mode stays in it. Do not reverse the schema
migrations; they add tables and columns and fill them.

## 7. Checks

```bash
cd backend && python -m pytest tests/test_mfg_*.py --nomigrations --create-db -q     # about 440 tests
python scripts/ci_gates/run_guards.py                                                # includes guard_no_direct_stock_writes
cd web && npx tsc -b && npx eslint src && npx vitest run
```

Race tests (`test_mfg_concurrency_postgres.py`) run only against PostgreSQL. The browser journeys are in
`web/e2e-golden/manufacturing-golden.spec.ts` (`npm run test:e2e:golden`).
