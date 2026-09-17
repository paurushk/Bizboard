# Training outline A1–A26 (17.3)

One sitting per capability. Demo data only. No GST legal opinions.

| Id | Teach | Show | Do not say |
|---|---|---|---|
| A1 | Intra-state invoice | Draft → lines → Complete → stock ↓, CGST/SGST, AR | “This is your GSTR-1 filed” |
| A2 | Inter-state | Place of supply → IGST | “POS always follows GSTIN” as law |
| A3 | Non-GST / nil | Zero tax, totals still consistent | “Nil-rated means exempt always” |
| A4 | Quotation | Convert; no stock until invoice completes | |
| A5 | Sales return / CN | Against completed invoice; stock ↑ | “Use a return to fix price” (use H9) |
| A6 | Purchase (no GRN) | Complete posts stock **and** AP | |
| A7 | Purchase return | Against completed purchase | |
| A8 | Product lookup | SKU / name / barcode, this company only | |
| A9 | Stock movements | Append-only; balance = Σ movements | “FIFO layers” (C3) |
| A10 | Customer receipt | Allocate; over-allocation rejected | |
| A11 | Supplier payment | Allocate to bills | |
| A12 | Ledgers | Derived, not a separate table | |
| A13 | Reports | TB / P&L / BS / stock / registers | |
| A14 | PDF | Totals + tax breakup; 409 while generating | |
| A15 | Imports | Excel/CSV; re-run is idempotent | “CSV IDs” as the identifier scheme |
| A16 | Exports | Matches source rows | |
| A17 | RBAC | Staff flags vs Owner | “Support will impersonate Staff” |
| A18 | Isolation | Tenant A cannot open tenant B ids | “RLS is on in prod” (it is not) |
| A19 | Onboarding | Register → `/setup` | |
| A20 | Auth | Login / logout / session | Share passwords in chat |
| A21 | Period close | Back-date rejected; H9 reverse+repost | |
| A22 | Money | Decimal strings, no float | |
| A23 | POS | Checkout → invoice → stock → GST → cash/UPI | Manufacturing from POS |
| A24 | TDS/TCS | 194Q / 206C on the document | CA opinion |
| A25 | Online collect | Sandbox webhook → receipt; replay no-op | Live settlement |
| A26 | OTP | Request → verify; hashed at rest | Enable `OTP_DEBUG_ECHO` in prod |

Table B dark modules stay off. Homework: one complete invoice + PDF + receipt
allocation on staging, not production.
