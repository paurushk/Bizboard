# Pilot Agreement — Outline (not legal copy)

**Plan ref:** SR-57. **Status:** working defaults below; **PO / legal to convert to the signed form.**
This is an outline of terms to cover, not a contract. Do not present this file to a merchant as-is.

---

## 1. Parties & scope

- Operator (Bizboard host) and the pilot firm (single legal entity, one GSTIN).
- Purpose: evaluate Bizboard for the firm's day-to-day B2B trade billing, inventory and ledgers.
- Term: **4 weeks** from onboarding completion, extendable by mutual written agreement.
- Fee: **none** for the pilot term.

## 2. What the firm gets

- Access for the owner + up to the firm's staff seats.
- Onboarding support, weekly check-ins, and blocking-bug fixes during the term (see `SUPPORT_SLA.md`).
- The full feature set in frozen pilot scope (billing, inventory, derived ledgers, receipts + allocation, month-end GSTR-1/3B + trial balance worksheets).

## 3. What the firm does

- Uses Bizboard as the primary system for the trade loop for the term.
- Gives feedback on the weekly calls and does one month-end close with its CA.
- Provides accurate masters and opening balances.

## 4. Data

- **Ownership:** all data the firm enters remains the firm's.
- **Export:** full company data export available on request at any time, and at term end, in a documented format.
- **Erasure:** on written request, the firm's data is erased (automated erasure — D13 — once SR-42 ships; support-ticket erasure until then). Statutory tax documents are retained anonymised for the legal retention period, then purged — **final retention policy per founder decision SR-40; working default 8 years.**
- **Processing:** data is used only to operate the service for the firm. Subprocessors per `DPDP_POSTURE.md`.
- **Isolation:** the firm's data is company-scoped and not visible to other pilot firms.

## 5. Statutory disclaimer (must be explicit)

- GSTR-1 / GSTR-3B / CMP-08 outputs are **calculation worksheets** for the firm/CA to file on the GST portal — **not** live GSP portal filing.
- e-invoice / e-way outputs (where shown) are **preview / manual-record only** — Bizboard does not generate live IRNs or e-way bills in the pilot.
- Online payments (if enabled) run in **sandbox**, not live settlement.
- The firm remains responsible for its own statutory compliance and filings.

## 6. No warranty / liability

- Pilot software provided "as is"; no uptime or fitness warranty for the pilot term.
- Liability cap and indemnities: **legal to set.**

## 7. Exit

- Either party may end the pilot with written notice.
- On exit: data export provided; on request, data erased per §4.
- No obligation on either side to continue to a paid plan.

## 8. Open items for legal / PO

- Governing law / jurisdiction.
- Liability cap, indemnity, confidentiality clause wording.
- Whether a DPA / processor addendum is attached.
- Signature blocks and effective date.
