# Personas and Jobs To Be Done (UX programme, Phase 0.5)

Source: `docs/BUSINESS_ARCHETYPES_AND_PERSONAS.md` (P1–P6, ARCH-01…07) and `USER_ROLE_COVERAGE.md` (roles, reconciled 2026-09-27). This file maps them to journeys J1–J10 in `docs/UX_MASTER_EXECUTION_PLAN.md`. JTBD statements are hypotheses until the Phase 1 user sessions.

## Persona to role to journeys

| Persona | System role | Context and stress | Primary journeys |
|---|---|---|---|
| P1 Managing Proprietor ("Sethji") | OWNER | Time-poor, cash-flow anxiety, often does every job (Model A). Distrusts what he cannot see | J1, J2, J5, J10 (also J3/J4 when solo) |
| P2 Counter Clerk | SALES_STAFF (POS) | Queue pressure, barcode scanner, keyboard-first, low tolerance for modals | J3 |
| P3 Field Order Booker | SALES_STAFF | Mobile, patchy network, books orders at customer site | J4 on mobile, offline outbox |
| P4 Godown Custodian | INVENTORY_STAFF | Physical stock, batch and serial, godown transfers, gloves and dust | J6 (inward), J7 |
| P5 Resident Bookkeeper ("Munshi") | ACCOUNTANT / MANAGER | Ledger accuracy, Tally habits, month-end pressure | J5, J6, J8, J9 |
| P6 External CA | AUDITOR / ACCOUNTANT | Periodic, wants clean GST and books, exports | J9 |
| (Support) VIEWER, POLICY_DESK | VIEWER, POLICY_DESK | Read-only, create actions hidden | J10 |

Archetypes that shape default flows: ARCH-01 counter retail (POS first), ARCH-03 semi-wholesaler (B2B credit; the leading pilot hypothesis in the archetypes doc), ARCH-05 batch/expiry (pharma, FMCG), ARCH-06 serialized goods.

## Jobs To Be Done

Format: "When [situation], I want to [motivation], so I can [outcome]."

### P1 Proprietor
1. When I open the app in the morning, I want to see what needs me today (dues, low stock, blocked setup), so I can act in five minutes. (J10)
2. When a customer owes me, I want to chase and record the payment fast, so cash comes in. (J5)
3. When I set up the shop, I want to reach my first real bill quickly, so I trust the product. (J1, J2)
4. When the month ends, I want my CA to have what they need without back-and-forth. (J9)
5. When staff make a mistake, I want it caught before it becomes wrong books. (all)

### P2 Counter clerk
1. When a customer is waiting, I want to scan, total, take payment and print in seconds, without touching the mouse. (J3)
2. When a customer changes their mind or steps away, I want to hold the bill and come back. (J3)
3. When something blocks the sale (batch, credit, stock), I want to know why and the one thing to do. (J3)
4. When the network drops, I want to keep selling and not lose the bill. (J3, J10)

### P3 Order booker
1. When I am at a customer, I want to build an order on my phone including their price and credit position. (J4)
2. When I have no signal, I want to save it and have it sync later, visibly. (J10)

### P4 Godown custodian
1. When a supplier delivery arrives, I want to record what was received with batch and expiry, so stock is right. (J6, J7)
2. When goods move between godowns, I want to transfer and reconcile differences. (J7)
3. When I count stock, I want to find variances and fix them formally. (J7)

### P5 Bookkeeper
1. When a receipt arrives, I want to allocate it to the right invoices quickly. (J5)
2. When a supplier bill arrives, I want to enter or upload it once and get GST and ITC right. (J6)
3. When a customer returns goods, I want a credit note that reverses correctly. (J8)
4. When I close the period, I want checks, reconciliation and locked books. (J9)

### P6 External CA
1. When I review, I want GSTR-1/3B data and reconciliation with GSTR-2B I can trust. (J9)
2. When something is missing, I want a clear list of missing documents. (J9)

## Feature-flag and pack variation (affects every audit)

Navigation is gated by permission, runtime flags, `ALWAYS_HIDDEN_NAV` (bills-of-entry, telegram, fixed-assets, tickets, shared-tickets, insurance, contracts) and `PACK_HIDDEN_SECTIONS` (insights, manufacturing, payroll, crm, complaints, job cards, projects and so on for new companies on the archetype pack sidebar). Each audit pass must be run in at least three configurations:
1. Solo owner, new company, archetype pack sidebar (P1 first-run).
2. Counter pair: OWNER plus SALES_STAFF on POS.
3. Trade firm: OWNER, SALES_STAFF, INVENTORY_STAFF, ACCOUNTANT with the full sidebar.

## Open questions for Phase 1 sessions
- Do owners open the app daily, or only when something is wrong?
- What words do they use for Receipts, Supplier payments, Godown vs. Warehouse, Challan? (feeds the glossary)
- How many run POS on a low-end Android device vs. a desktop with a scanner?
