"""Build the trackable implementation plan sheets in the Task Register workbook (v2, after the 63 pre-implementation questions).

usage: python qos/evidence/build_plan.py <workbook.xlsx>      (recalculate in Excel afterwards)

Sheets written: Plan guide, Plan decisions, Implementation plan, Plan rollup, Plan by week, Plan milestones, Plan change log.
Re-running replaces those sheets, so copy any input cells (stage status, actual dates, links) first. WI ids are kept stable
across runs: they are read back from the existing plan sheet by plan key.
"""
import copy
import math
import sys
from datetime import date, timedelta
from pathlib import Path

import openpyxl
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter as L
from openpyxl.worksheet.datavalidation import DataValidation

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from plan_decisions import QA  # noqa: E402

START = date(2026, 10, 12)  # Monday
LANES = 2  # agent lanes; the human decides and reviews
BUFFER = 0.20
HOLIDAYS = {date(2026, 10, 20), date(2026, 11, 9), date(2026, 11, 11), date(2026, 11, 24), date(2026, 12, 25), date(2027, 1, 26)}
NAVY = "FF1F497D"
BI, BP, BL = "Build in MVP", "Build in Pilot", "Build in GA"
WAVE = {BI: 1, BP: 2, BL: 3}
GATE = {1: "MVP", 2: "Pilot", 3: "Later"}
OWNERS = ["Agent 1", "Agent 2", "Human reviewer", "Founder", "CA / external"]

src = (HERE / "apply_decisions.py").read_text(encoding="utf-8")
ns: dict = {}
exec(src[src.index("BI, BP, BL, P ="): src.index("P0D = {")], {}, ns)
DECIDED = ns["MVP"]  # task -> (decision, days, scope)
DROPPED = {"C-0614": 60, "X-0522": 60, "C-0617": 62, "C-0619": 63}  # task -> question that dropped it

AUD, SEC, GST, PAY, INV, PLT, GRO, QG = ("Audit & integrity", "Security", "GST & compliance", "Payments & credit", "Inventory & POS",
                                         "Platform & reliability", "Growth & SaaS", "Quality gate")
WS = {}
for ids, w in {
    AUD: "P-0115 X-0432 P-0507 C-0616 S-0561 X-0715 S-0568 CUST-LOCK CA-SIGN",
    SEC: "SEC-0622 SEC-0624 SEC-0625 SEC-0626 SEC-0628 S-0572",
    GST: "C-0609 C-0602 C-0603 C-0604 P-0503 C-0607 X-0514 X-0515 C-0618 C-0606 X-0706 DEC-CA",
    PAY: "X-0527 X-0530 X-0713 X-0707 P-0128 P-0152 X-0702 P-0119",
    INV: "P-0046 P-0052 P-0081 P-0089 P-0180 UX-0596 I-0651 I-0655 R-0636 R-0636b S-0562 UX-0581 UX-0582 UX-0586 UX-0588 UX-0590 UX-0591",
    PLT: "S-0570 S-0579 S-0574 REG-WEB DEC-HOST",
    GRO: "SaaS-0669 D-0684 D-0690 D-0693 SaaS-0666 GOS-0721 GOS-0737 GOS-0739",
}.items():
    for t in w.split():
        WS[t] = ids
WEB = set("UX-0596 UX-0581 UX-0582 UX-0586 UX-0588 UX-0590 UX-0591 I-0651 I-0655".split())
KIND = {k: "web" for k in WEB}
KIND.update({"R-0636": "perf", "R-0636b": "perf", "S-0570": "infra drill", "S-0579": "infra drill", "DEC-HOST": "decision",
             "DEC-CA": "decision", "CA-SIGN": "external", "REG-WEB": "tooling", "S-0572": "feature"})
FULL_STACK_BACKEND = set("P-0115 X-0432 P-0507 C-0616 S-0561 S-0568 SEC-0622 SEC-0625 SEC-0626 SEC-0628 X-0715 CUST-LOCK S-0562 "
                         "GOS-0721 GOS-0737 GOS-0739 S-0574 D-0690 R-0636 R-0636b".split())
INFRA = set("S-0570 S-0572 S-0579".split())

# estimate changes after the 63 questions (days)
EST = {"SEC-0624": 4, "R-0636": 2, "I-0651": 6, "I-0655": 2, "D-0693": 25, "C-0606": 2}
SCOPE = {
 "P-0115": "Audit event with actor, IP and before/after values on: sales invoice complete, cancel, amend; sales return; credit and debit notes; purchase invoice complete (books on and off); purchase return; customer receipt; supplier payment; journal post and reverse; stock adjustment, transfer, goods receipt; payroll finalise; period lock and reopen. One test per action; remove the xfails.",
 "P-0507": "Rule 11(g) coverage map (action to audit event) built now; edit log on every accounting record; certification export listing the periods in which logging was on. CA sign-off is the separate CA-SIGN item.",
 "S-0561": "Nightly worker runs these invariants: trial balance zero; every journal balanced; AR/AP control accounts equal customer/supplier outstanding; stock ledger equals movements; allocations within payments; ledger output tax equals invoice tax. A violation creates a quarantine record, blocks period close and GST export until cleared (billing continues), and alerts Owner, Accountant and the ops mailbox.",
 "S-0568": "is_deleted on Customer, Supplier, Product, Warehouse and PriceList; restore by Owner/Admin; ledger accounts keep their guard; transactions are cancelled, never soft-deleted. Cascades onto transactional rows become PROTECT; existing child rows untouched; an orphan report is produced before the migration.",
 "S-0570": "Provider-specific design after DEC-HOST: WAL archiving and point-in-time recovery plus the daily encrypted dump, RPO 5 min and RTO 1 h by default, keys held in the provider key service. Restore drill into a non-production copy, timed.",
 "S-0572": "Redis token bucket. Login 10/min per IP and 5/min per account; OTP 3/min and 10/h per target; register 5/h per IP; portal 60/min per token; authenticated API 600/min per tenant (burst 100); webhooks signature-verified with a higher limit. Redis down: login and OTP fail closed on a strict in-process limit, the general API fails open, with an alert.",
 "SEC-0622": "Omit purchase_price and margin (never blank or zero) in API, exports and PDFs for Cashier, Salesperson and Godown custodian; visible to Owner, Admin, Accountant, Purchase Manager, Inventory Manager. POS shows a server-computed below-cost warning, not the cost.",
 "SEC-0624": "Gap-fill, not a rebuild. Enforcement already defaults on in production and staging for OWNER and ACCOUNTANT, with first-login enrolment and recovery codes. There is no separate Admin role (OWNER is Owner/Admin) and no can_manage_users flag. Extend the same enforcement to any membership with can_post_journals (MANAGER by default). Leave SALES_STAFF, inventory staff, auditor and viewer out.",
 "SEC-0625": "Per-user session version checked on each request (Redis with database fallback) plus the existing refresh blacklist, so access and refresh tokens both die on deactivation. Websocket drop only if a channel layer exists.",
 "SEC-0626": "Strip HTML tags on save from plain-text fields (notes, descriptions, names, addresses, remarks, complaint text, imported cells); escape on render and in PDF templates; a guard test fails on string-built raw SQL.",
 "SEC-0628": "AES-256-GCM with a key id for bank account numbers and tax-portal secrets; move existing gateway credentials off Fernet. IFSC stays plain. Batch migration of plaintext rows (reversible), last four digits kept for display. Keys from the host secret store.",
 "X-0715": "Snapshot legal name, trade name, billing and shipping address and GSTIN at completion on sales invoices, credit and debit notes and purchase bills. Backfill flags rows as backfill_from_master and uses the audit-history name as of the invoice date where a rename exists.",
 "C-0609": "Per-tenant pharmacy flag, default off. Schedule H/H1/X sale cannot complete without patient and prescriber name and registration no.; Schedule X keeps a prescription copy. Inspector layout (date, patient, prescriber, drug, batch, quantity, invoice no.) as PDF and CSV; retention default 3 years, configurable. A licensed pharmacist reviews layout and retention before any pharmacy goes live.",
 "C-0602": "Per-bill checklist: invoice held and goods received and 180-day payment are system-proven; supplier-paid-tax and return-filed are user-attested (GSTR-2B is outside the freeze). Unconfirmed bills warn and drop out of the claimable ITC summary; posting is not blocked. CA reviews wording.",
 "C-0603": "Warnings 60 and 7 days before the s.16(4) deadline (30 Nov after the invoice's financial year, or annual return date if earlier); TIME_BARRED after it for unclaimed ITC, excluded from claimable. Claimed ITC is flagged for the CA, not reversed.",
 "C-0604": "Data-driven s.17(5) rule table with effective dates covering the full blocked list; match on HSN/SAC plus expense category (keywords only suggest); blocked GST posts to expense or asset, not ITC receivable; override by Owner or Accountant with reason, audited. CA approves the table.",
 "P-0503": "Add the blocked-credit classification to the existing 2A/2B reconciliation using uploaded 2B files. No new reconciliation, no GSTN call.",
 "C-0607": "Section 50 worksheet and CSV: 18% a year on late-paid tax, 24% on undue or excess ITC; net cash liability basis for late-filed returns (Rule 88B), unpaid amount otherwise. Rates in a dated table. No journal posted. CA confirms.",
 "X-0527": "Keep the existing hold and add the chronic rule; the stricter one wins. Existing, always on: invoice complete blocks when credit_limit > 0 and exposure plus the invoice exceeds it. Existing, opt-in and default off (auto_credit_hold_on_severe_overdue): invoice complete also blocks stop_credit (outstanding above the limit) or overdue_severe (any overdue and either 90-plus days or average payment delay over 21 days). New, per company: any invoice over 60 days overdue and an over-60-day total of at least Rs 5,000 also blocks credit-sale completion, sales-order confirmation and delivery challans. Cash and prepaid still allowed. Single-use unlock code valid 24 h from the Owner or credit-override role, with reason.",
 "X-0530": "Bounce voids the receipt, reverses allocations, debits the bank fee (amount from the bank memo, suggested Rs 500) to the customer and alerts the owner. GST on the recovery is a configurable flag, default off.",
 "X-0713": "Section 138 notice draft only: written demand within 30 days of the bank memo, 15 days to pay, dates from the memo, disclaimer that an advocate must review. No reversal or fee logic here.",
 "X-0707": "Status from the existing alert source plus a manual flag. New ITC blocked for invoices dated on or after the cancellation effective date; availed ITC flagged for the CA; payment hold overridable by Owner or Accountant with reason, audited.",
 "P-0128": "Queue for: credit-limit override, stock adjustment above threshold, invoice cancel or amend after completion, discount above threshold, return or credit note above threshold, backdated posting or period reopen, supplier payment above threshold, write-off, bulk import commit. Default approver Owner, configurable per action; no self-approval except a flagged Owner exception; 72 h expiry counts as rejected.",
 "P-0152": "Stock adjustment needs a second user when value at cost is Rs 10,000 or more, or quantity is 10% or more of on-hand (both configurable per company), using the approval queue.",
 "X-0702": "In-app single-use 15-minute token bound to the invoice batch and requester (WhatsApp only when the freeze flag is flipped). No response: over-limit invoices stay Awaiting approval, others proceed, expiry counts as rejected, never auto-approved.",
 "R-0636": "Benchmark harness and recorded baseline for POS checkout complete (tax, stock and ledger included): 2 vCPU 4 GB container, local Postgres, 20,000 SKUs, 3-line cart, p95. Runs on its own nightly job, never in the pull-request run.",
 "X-0514": "Part B vehicle update as a stub action against the GSP adapter interface with a fake provider, plus stored vehicle history, behind GSP_LIVE_ENABLED=0. Live use needs sandbox credentials and a freeze exception.",
 "X-0515": "Validity extension as a stub action plus stored fields, same adapter and flag rule as X-0514.",
 "C-0618": "Part B time-limit alert and multi-vehicle split stored on the bill (stub action, GSP flag off).",
 "C-0606": "Validity computed from the user-entered distance using a configurable slab table with effective dates that the CA confirms. PIN-to-PIN distance lookup is deferred (needs NIC).",
 "X-0706": "Transfer vehicle-breakdown Part B workflow on stock transfers as a stub action plus stored fields (GSP flag off).",
 "P-0046": "Optional salt, composition and manufacturer fields on products, searchable at billing with a trigram index inside the checkout latency budget (query-budget test).",
 "P-0052": "CSV with invoice ref, customer, dates, SKU or barcode, quantity, rate, discount %, warehouse, notes; dry run, then per-invoice atomic commit; any bad row rejects that invoice and is reported by row; 2,000-row cap; file hash makes re-upload idempotent.",
 "P-0081": "In-transit location per transfer: dispatch moves source to in-transit, receipt moves it to destination; partial receipt with shortage or damage reason; no ledger entry for same-company, same-GSTIN transfers.",
 "P-0089": "Per-warehouse breakdown and switching inside one company on the dashboard, inside the dashboard query budget (test). Multi-company GSTIN stays out of scope.",
 "P-0119": "Report only: interest exposure (default 18% a year simple, per company) and suggested provision by age (0-60 d 0%, 61-90 d 5%, 91-180 d 25%, 181-365 d 50%, over 365 d 100%). No posting.",
 "P-0180": "Users map to many warehouses with one default; contact person and phone required, email optional.",
 "I-0651": "Network ESC/POS printer through a print bridge, with PDF fallback. Bluetooth deferred. Verified on a real network ESC/POS printer (for example Epson TM-T82) that you provide.",
 "I-0655": "USB keyboard-wedge timing heuristic. Browser camera scanner deferred (mobile camera scan already works).",
 "SaaS-0669": "Bizboard's own GST invoice to the tenant (our GSTIN, place of supply from the tenant's state), generated and emailed when a Cashfree or PayU payment is captured (freeze D3: sandbox, at least one of those two). No gateway SDK inside the invoice generator. Leave the existing Razorpay subscription reconciliation task alone.",
 "D-0684": "Per-debtor bootstrap of days-late from the last 12 settled invoices, shrunk to the segment average, 1,000 runs, show p10/p50/p90; under 5 settled invoices fall back to the ageing heuristic with a low-confidence badge.",
 "D-0690": "Score at least 0.95 with equal GSTIN and tax within tolerance links automatically; 0.80 to 0.95 suggests; below 0.80 shows nothing. Runs on uploaded 2B data after P-0503.",
 "D-0693": "TallyPrime only: ledger masters, stock items, opening balances and one financial year of vouchers with a mandatory ledger and stock-item mapping step. ENABLE_TALLY stays off; flipping it is a separate freeze exception.",
 "UX-0596": "Typed-confirmation input on destructive dialogs.",
}
# key, register task, title, wave, days, scope
EXTRA = [
    ("REG-WEB", "", "Extend register_sync.py to score Vitest and Playwright results", 1, 1,
     "Parse Vitest and Playwright JUnit, map web test file paths to register rows, unit-test the parser against real output."),
    ("DEC-HOST", "", "Decide Postgres host, RPO/RTO and backup-key custody", 1, 0.5,
     "Founder chooses the provider (default: managed Postgres in an India region with point-in-time recovery), confirms RPO 5 min and RTO 1 h, and names the key administrator."),
    ("DEC-CA", "", "Engage a chartered accountant for Rule 11(g) and the tax rule tables", 1, 0.5,
     "Name the CA and agree the review scope: Rule 11(g) coverage, s.16(2), s.16(4), s.17(5), s.50 tables, e-way validity slabs, bad-debt buckets."),
    ("CA-SIGN", "", "CA sign-off of the Rule 11(g) coverage map", 1, 1,
     "CA reviews the coverage map and certification export and signs. Lead time five working days."),
    ("CUST-LOCK", "", "Concurrent customer edits: field merge plus version check", 1, 2,
     "PATCH merges changed fields under a row lock so concurrent edits of different fields both persist; PUT requires a version and a stale write returns 409 with the current value. Create the register row when starting. Remove the strict xfail in test_register_race_gaps.py."),
    ("S-0579", "S-0579", "Production check and alert for the nightly audit-chain seal", 1, 0.5,
     "The seal task is already on the Celery beat at 02:40. A verify failure only logs an error (Sentry if configured); nothing notices a night that never ran, and there is no seal email. Add a missed-run check that logs an error and sends the Owner the same in-app notification the nightly invariant task already uses."),
    ("R-0636b", "", "Optimise POS checkout toward the 200 ms p95 target", 1, 5,
     "Timeboxed to 5 days after the baseline from R-0636: profile, fix the top costs, record the new p95. If the target is not met the remaining gap is reported, not hidden."),
    ("GOS-0721", "GOS-0721", "End-to-end test: inbound lead de-duplication", 2, 1, "End-to-end test through the API; fixing a failing flow is in scope up to one day."),
    ("GOS-0737", "GOS-0737", "End-to-end test: complaint to credit note, return or replacement", 2, 1, "End-to-end test with stock and ledger check; credit note created exactly once."),
    ("GOS-0739", "GOS-0739", "End-to-end test: supplier complaint to purchase debit note", 2, 1, "End-to-end test with stock and ledger check."),
    ("SaaS-0666", "SaaS-0666", "End-to-end and load test of tenant signup and provisioning", 2, 3,
     "Signup to workspace end to end; load test of 20 concurrent out of 50 signups, p95 provisioning at most 10 s, no duplicate tenants; nightly or manual, not in the pull-request run."),
    ("S-0562", "S-0562", "Release orphaned stock allocations on expired cart sessions", 2, 2,
     "No cart session or timeout exists. POS drafts are device-local and do not reserve stock. Add a company-configurable expiry (default 24 hours, confirm before starting) on confirmed sales-order reservations and on POS holds from UX-0582: release the allocation and mark the hold expired, keeping the row."),
    ("UX-0581", "UX-0581", "Keyboard-only POS navigation", 2, 3, "Complete keyboard navigation of the POS flow."),
    ("UX-0582", "UX-0582", "Multi-cart hold and recall at POS", 2, 3, "Hold and recall several carts without losing stock reservations. Reservations use the expiry job from S-0562."),
    ("UX-0586", "UX-0586", "Ctrl+K omnibar", 2, 2, "Global command palette with search and actions."),
    ("UX-0588", "UX-0588", "Warehouse rack locator badge", 2, 2, "Rack or bin location on stock and picking views."),
    ("UX-0590", "UX-0590", "Bulk import progress bar with time remaining", 2, 2, "Progress and ETA for long imports."),
    ("UX-0591", "UX-0591", "Privacy mask for rupee figures", 2, 1, "Personal on-screen toggle, separate from role masking; not a security control."),
    ("S-0574", "S-0574", "Anomaly detector for unusual discounts and bill amounts", 3, 8,
     "Review queue only, never blocks a bill. Unusual: discount above 3 times the item's median discount, or a bill above both a rupee floor and 3 times the customer's median bill; thresholds per company."),
]
DEPS = {"X-0432": ["P-0115"], "P-0507": ["P-0115"], "CA-SIGN": ["P-0507", "DEC-CA"], "C-0616": ["P-0507"], "P-0152": ["P-0128"],
        "X-0702": ["P-0128"], "P-0503": ["C-0604"], "C-0603": ["C-0602"], "X-0713": ["X-0530"], "C-0618": ["X-0514"],
        "X-0515": ["X-0514"], "X-0706": ["X-0514", "P-0081"], "S-0570": ["DEC-HOST"], "R-0636b": ["R-0636"], "D-0690": ["P-0503"],
        "UX-0582": ["S-0562"],
        "C-0602": ["DEC-CA"], "C-0604": ["DEC-CA"], "C-0607": ["DEC-CA"], "C-0609": ["DEC-CA"]}
for k in WEB:
    DEPS.setdefault(k, [])
    if "REG-WEB" not in DEPS[k]:
        DEPS[k].append("REG-WEB")
QREF = {"P-0115": "19", "X-0432": "10", "P-0507": "7, 10", "CA-SIGN": "7", "S-0561": "22", "S-0568": "23", "S-0570": "6", "S-0572": "24",
        "SEC-0622": "25", "SEC-0624": "12, 18", "SEC-0625": "26", "SEC-0626": "27", "SEC-0628": "20", "X-0715": "28", "C-0609": "29",
        "C-0602": "30", "C-0603": "31", "C-0604": "32", "P-0503": "33", "C-0607": "34", "X-0527": "35", "X-0530": "36", "X-0713": "36",
        "X-0707": "37", "P-0128": "38", "P-0152": "39", "X-0702": "40", "R-0636": "41", "R-0636b": "17, 41", "X-0514": "42", "X-0515": "42",
        "C-0618": "42", "C-0606": "42", "X-0706": "42", "CUST-LOCK": "11, 43", "S-0579": "21", "P-0046": "44", "P-0052": "45", "P-0081": "46",
        "P-0089": "47", "P-0119": "48", "P-0180": "49", "I-0651": "50", "I-0655": "50", "SaaS-0669": "51", "GOS-0721": "52", "GOS-0737": "52",
        "GOS-0739": "52", "SaaS-0666": "53", "S-0562": "54", "UX-0582": "55", "UX-0591": "56", "D-0684": "57", "D-0690": "58", "D-0693": "59",
        "S-0574": "61", "REG-WEB": "9", "DEC-HOST": "6", "DEC-CA": "7", "UX-0596": "9", "UX-0581": "9"}
CUT = {"C-0618": 1, "X-0515": 2, "C-0606": 3, "X-0713": 4, "X-0707": 5, "C-0604": 6, "P-0503": 7, "X-0527": 8, "R-0636b": 9, "SEC-0626": 10}
# (pass condition, rejecting case) per item; items not listed get a template by kind
PASS = {
 "P-0115": ("Every action in the scope list writes exactly one AuditEvent with actor, IP and before/after; the chain verifies", "A journal post or a purchase complete with books off that writes no event fails its test (the current xfails); a tampered event fails verification"),
 "X-0432": ("Parent P-0115 is Done and its tests pass", "Same rejecting cases as P-0115"),
 "P-0507": ("Coverage map lists every accounting record with its event; certification export shows logging on for the whole year", "Export refuses to certify when the chain has a gap or logging was off in a period"),
 "CA-SIGN": ("Signed note from the CA attached as evidence", "No sign-off by M1: milestone marked 'pilot with documented residual'"),
 "C-0616": ("Report certifies logging was never disabled for the financial year", "Report flags any window in which logging was disabled"),
 "S-0561": ("Nightly task runs every listed invariant; a violation creates a quarantine record, blocks period close and GST export and alerts", "An unbalanced journal inserted through the ORM is caught on the next run and blocks period close"),
 "S-0568": ("Soft-deleted masters vanish from lists, reports and search and Owner/Admin can restore them with history intact", "Hard delete of a master that has transactions raises; deleting a parent no longer cascades onto transactional rows"),
 "S-0570": ("Timed restore drill reaches a chosen target time within the RTO; the encrypted dump restores", "Restore with the wrong key fails; a gap in archived WAL raises an alert"),
 "S-0572": ("Each public route enforces its limit with 429 and Retry-After", "The 11th login attempt in a minute is refused; with Redis stopped, login still refuses over-limit attempts and the general API stays up"),
 "SEC-0622": ("Cashier, Salesperson and Godown custodian never receive purchase price or margin from API, exports, PDFs or POS", "A request from those roles for cost fields gets the field omitted, with one test per surface"),
 "SEC-0624": ("OWNER, ACCOUNTANT and a membership with can_post_journals cannot get a normal session without TOTP, are forced to enrol at first login, and recovery codes work once", "Password-only login for those memberships yields no session; SALES_STAFF can still sign in with a password"),
 "SEC-0625": ("Deactivating a user invalidates access and refresh tokens at the next request", "A deactivated user's existing access token is answered 401"),
 "SEC-0626": ("HTML is stripped on save from the listed fields and output is escaped in the UI and PDFs", "A stored script tag never executes or appears raw; string-built raw SQL fails the guard test"),
 "SEC-0628": ("Bank account numbers and portal secrets are AES-256-GCM encrypted with a key id and migrated from plaintext", "Tampered ciphertext fails authentication; the wrong key is rejected; no plaintext column remains"),
 "X-0715": ("Completed documents keep the party details as at completion", "Renaming the customer afterwards does not change the issued PDF or ledger view"),
 "C-0609": ("A Schedule H/H1/X sale cannot complete without the required details and the register prints in inspector layout", "A sale without the details is rejected; a tenant without the pharmacy flag is unaffected"),
 "C-0602": ("The checklist shows on every purchase bill with proven and attested conditions", "A bill with an unconfirmed condition is excluded from the claimable ITC summary"),
 "C-0603": ("Warnings appear at 60 and 7 days before the deadline; barred ITC is marked TIME_BARRED", "TIME_BARRED ITC cannot be claimed; ITC already claimed is flagged, not reversed"),
 "C-0604": ("Blocked purchases post GST to expense or asset; the rule table covers the full list", "Claiming a blocked category without an authorised override and reason is refused"),
 "P-0503": ("The 2B reconciliation shows the blocked-credit classification", "A blocked invoice is never counted as eligible ITC"),
 "C-0607": ("Worksheet interest matches hand-calculated cases for each rate and period", "A date outside the rate table is refused; no journal is posted"),
 "X-0527": ("Chronic customers are blocked from credit sale, order confirmation and challan; cash sales pass; the existing hold still works", "A used or expired unlock code fails; a blocked customer cannot take a credit sale"),
 "X-0530": ("A bounce voids the receipt, reopens the invoice, debits the fee and alerts the owner", "Bouncing the same receipt twice is rejected"),
 "X-0713": ("Notice draft carries the right dates and the disclaimer", "Dates outside the statutory sequence are refused"),
 "X-0707": ("Invoices dated on or after the cancellation date are excluded from ITC and the supplier payment is held", "A held payment cannot post without an authorised override"),
 "P-0128": ("Listed actions enter the queue; approve and reject are audited; requests expire at 72 h", "A requester cannot approve their own request (except the flagged Owner exception)"),
 "P-0152": ("An adjustment over threshold needs a second user's approval", "The same user approving is rejected"),
 "X-0702": ("A single-use 15-minute token releases the over-limit invoices", "A reused or expired token fails; no response leaves the invoice held, never approved"),
 "R-0636": ("Harness produces a repeatable p95 on the stated hardware and catalogue and records the baseline", "A run that regresses more than 15% against the baseline fails the nightly job (not the pull-request run)"),
 "R-0636b": ("p95 at or below 200 ms, or the remaining gap and its causes are reported", "A change that worsens p95 against the new baseline is rejected by the nightly job"),
 "X-0514": ("Part B update stored with history; stub action works against the fake provider", "Update on a cancelled or expired bill is refused"),
 "X-0515": ("Extension stored and allowed inside its window", "Extension outside the window is refused"),
 "C-0618": ("Alert fires at the Part B limit; split stored", "Split quantities above the consignment are rejected"),
 "C-0606": ("Validity from distance matches the slab table at the 100, 200 and 201 km boundaries", "Zero or negative distance is rejected"),
 "X-0706": ("Transfer Part B update stored", "Update on a completed transfer is refused"),
 "CUST-LOCK": ("PATCH merges concurrent field edits and PUT with the current version succeeds", "A stale PUT returns 409 and changes nothing (the strict xfail test now passes)"),
 "S-0579": ("A missed night logs an error and creates an in-app notification for the Owner", "Disabling the scheduled task in a test makes that alert fire; a successful seal does not"),
 "SaaS-0669": ("A captured Cashfree or PayU payment produces one GST invoice to the tenant and emails it", "A second delivery of the same capture does not create a second invoice; Razorpay reconciliation is unchanged"),
 "S-0562": ("A reservation older than the company TTL releases its stock and is marked expired, and the row remains", "A reservation inside the TTL is left allocated; an expired hold does not delete the order or cart"),
 "DEC-HOST": ("Provider, RPO, RTO and key administrator recorded", "S-0570 does not start until this is recorded"),
 "DEC-CA": ("CA named and review scope agreed in writing", "Tax rule items do not close without CA review"),
 "REG-WEB": ("register_sync.py scores Vitest and Playwright results onto register rows", "A web test that fails marks its row Fail; an unknown path is reported as unmatched"),
 "UX-0596": ("The destructive button stays disabled until the exact text is typed", "A wrong or partial text keeps it disabled; keyboard and screen-reader path tested"),
}
DOD = {
 "feature": "tests for the touched apps pass on Postgres 17 with lint and type checks clean and any strict xfail for the item removed; the reviewer (not the author) signs; register_sync.py scores the test and the register row reads Built - tested / Pass; the full suite runs nightly and at the wave gate",
 "web": "Vitest (and Playwright where there is a flow) pass, tsc -b and ESLint report zero errors, the accessibility check is clean, and register_sync.py scores the web test; the backend suite is not required; the reviewer signs",
 "perf": "the benchmark job (outside the pull-request run) records the p95 against baseline and target and the report is attached as evidence; the reviewer signs",
 "infra drill": "the drill is executed on a non-production copy and its timings and steps are attached; the reviewer signs",
 "decision": "the decision is recorded in the Plan decisions sheet with date and owner",
 "external": "written sign-off from the external reviewer is attached as evidence",
 "tooling": "the tool runs on real output from the suites, its parser has unit tests, and the reviewer signs",
 "gate": "full backend suite green on Postgres, register_sync.py and register_drift.py clean, workbook recalculated with 0 formula errors, every item in the wave Done and reviewed",
}
TEMPLATE_REJECT = {"web": "invalid input keeps the action disabled; keyboard and screen-reader path tested",
                   "feature": "invalid input, a wrong-tenant request and a user without permission are each rejected, each with a test"}


def is_hol(d):
    return d.weekday() >= 5 or d in HOLIDAYS


def snap(d):
    while is_hol(d):
        d += timedelta(days=1)
    return d


def workdays(d, n):
    while n > 0:
        d += timedelta(days=1)
        if not is_hol(d):
            n -= 1
    return d


wb = openpyxl.load_workbook(sys.argv[1])
tr = wb["Task Register"]
head = {c.value: c.column for c in tr[1]}
rows = {tr.cell(r, 1).value: r for r in range(2, tr.max_row + 1)}
reg_title = {t: tr.cell(r, head["Task / Business Action"]).value for t, r in rows.items()}

# ---- keep WI ids stable
legacy = {}
if "Implementation plan" in wb.sheetnames:
    p = wb["Implementation plan"]
    ph = {c.value: c.column for c in p[4]}
    for r in range(5, p.max_row + 1):
        wid, t, ti = p.cell(r, 1).value, p.cell(r, 2).value, p.cell(r, 3).value or ""
        key = p.cell(r, ph["Plan key"]).value if "Plan key" in ph else None
        if not key:
            key = t or ("CUST-LOCK" if ti.startswith("Row lock") else f"VER-{p.cell(r, 4).value}" if "verification" in ti else None)
        if wid and key:
            legacy[key] = wid

# ---- item list
items = []
for tid, (dec, days, scope) in DECIDED.items():
    items.append(dict(key=tid, task=tid, title=reg_title[tid], wave=WAVE[dec], days=EST.get(tid, days), scope=SCOPE.get(tid, scope)))
for key, task, title, wave, days, scope in EXTRA:
    items.append(dict(key=key, task=task, title=title, wave=wave, days=days, scope=scope))
FIRST = {"REG-WEB": 0, "DEC-HOST": 1, "DEC-CA": 2}
order = {k: i for i, k in enumerate([i["key"] for i in items])}
items.sort(key=lambda i: (i["wave"], FIRST.get(i["key"], 9), order[i["key"]]))
for i in items:
    k = i["key"]
    i["ws"] = WS[k]
    i["kind"] = KIND.get(k, "feature")
    i["layer"] = ("Process" if i["kind"] in ("decision", "external") else "Tooling" if i["kind"] == "tooling" else "Infra" if k in INFRA
                  else "Web" if k in WEB and k not in ("I-0651", "I-0655") else "Web + device" if k in ("I-0651", "I-0655")
                  else "Backend" if k in FULL_STACK_BACKEND else "Full stack")
    i["deps"] = list(DEPS.get(k, []))
for w in (1, 2, 3):
    ver = dict(key=f"VER-{w}", task="", wave=w, days=2, ws=QG, layer="Process", kind="gate",
               title=f"Wave {w} verification: full suite on Postgres, register sync, drift check, {GATE[w]} gate review",
               scope="Run the full backend suite on Postgres, register_sync.py and register_drift.py, recalculate the workbook and review every wave item against its pass condition.",
               deps=[i["key"] for i in items if i["wave"] == w])
    items.append(ver)
    for i in items:
        if i["wave"] == w + 1 and not i["key"].startswith("VER"):
            i["deps"].append(f"VER-{w}")
items.sort(key=lambda i: (i["wave"], i["key"].startswith("VER"), FIRST.get(i["key"], 9), order.get(i["key"], 999)))
by_key = {i["key"]: i for i in items}
nxt = 68
for i in items:
    if i["key"] in legacy:
        i["id"] = legacy[i["key"]]
    elif i["key"] == "R-0636b":
        i["id"] = "WI-028b"
    else:
        i["id"] = f"WI-{nxt:03d}"
        nxt += 1
while any(sum(1 for j in items if j["id"] == i["id"]) > 1 for i in items):  # safety: re-run after ids collide
    raise SystemExit("duplicate WI ids")

# ---- schedule: LANES agent lanes; decisions and external items sit outside the lanes
free = [snap(START)] * LANES
for i in items:
    dep_end = max([workdays(by_key[d]["due"], 2) for d in i["deps"]], default=snap(START))  # one clear day for review
    i["planned"] = 5 if i["key"] == "CA-SIGN" else (math.ceil(i["days"] * (1 + BUFFER)) if i["days"] else 0)
    out_of_lane = i["kind"] in ("decision", "external")
    if not i["planned"]:
        i["start"] = i["due"] = dep_end
        i["owner"] = by_key[i["deps"][0]]["owner"] if i["deps"] else "Agent 1"
        continue
    if out_of_lane:
        i["start"], i["owner"] = snap(dep_end), ("Founder" if i["kind"] == "decision" else "CA / external")
        i["due"] = workdays(i["start"], i["planned"] - 1)
        continue
    cand = sorted((max(snap(free[d]), dep_end), d) for d in range(LANES))
    s, d = cand[0]
    i["start"], i["due"], i["owner"] = s, workdays(s, i["planned"] - 1), f"Agent {d + 1}"
    free[d] = workdays(i["due"], 1)

# ---- styles
FONT = "Calibri"
hfont, hfill = Font(name=FONT, size=11, bold=True, color="FFFFFFFF"), PatternFill("solid", fgColor=NAVY)
body = Font(name=FONT, size=10)
wrap = Alignment(wrap_text=True, vertical="top")
thin = Side(style="thin", color="FFBFBFBF")
box = Border(left=thin, right=thin, top=thin, bottom=thin)
inp = PatternFill("solid", fgColor="FFFFF8DC")


def fresh(name, idx):
    if name in wb.sheetnames:
        del wb[name]
    ws = wb.create_sheet(name, idx)
    ws.sheet_view.showGridLines = False
    return ws


def title(ws, text, sub):
    ws["A1"] = text
    ws["A1"].font = Font(name=FONT, size=16, bold=True)
    ws["A2"] = sub
    ws["A2"].font = Font(name=FONT, size=10, italic=True)
    ws["A2"].alignment = Alignment(wrap_text=True, vertical="top")


def header(ws, row, names, widths):
    for c, (n, w) in enumerate(zip(names, widths), 1):
        cell = ws.cell(row, c, n)
        cell.font, cell.fill, cell.border = hfont, hfill, box
        cell.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[L(c)].width = w


def fill(color):
    return PatternFill("solid", bgColor=color, fgColor=color)


base = wb.sheetnames.index("MVP scope after review") + 1
guide = fresh("Plan guide", base)
dec = fresh("Plan decisions", base + 1)
plan = fresh("Implementation plan", base + 2)
roll = fresh("Plan rollup", base + 3)
week = fresh("Plan by week", base + 4)
mile = fresh("Plan milestones", base + 5)
log = fresh("Plan change log", base + 6)

# ---- Plan guide
title(guide, "Implementation plan: guide", "How the plan is built, what each column means and how to keep it current.")
for r, (k, v, t) in enumerate([("Plan start (Monday)", START, "date"), ("Agent lanes assumed", LANES, "n"), ("Contingency buffer", BUFFER, "pct"),
                               ("Working days per week", 5, "n")], 4):
    guide.cell(r, 1, k).font = Font(name=FONT, size=10, bold=True)
    c = guide.cell(r, 2, v)
    c.font, c.fill, c.border = body, inp, box
    c.number_format = "dd-mmm-yyyy" if t == "date" else "0%" if t == "pct" else "0"
hol = ", ".join(d.strftime("%d %b %Y") for d in sorted(HOLIDAYS))
text = [
    ("What this is", f"One row per piece of work for the quality-first decisions of 2026-10-04. Revised after the 63 pre-implementation questions: see the Plan decisions sheet for every answer and what it changed. Each row has five stages (Design, Build, Tests, Review, Register sync); Status, percent done, days late and RAG are formulas driven by the stage cells and actual dates."),
    ("Team assumption", "One human owner plus agents (default; confirm). Two agent lanes run in parallel only on independent items, each in its own git worktree and Postgres database. Decisions and external reviews sit outside the lanes. Change LANES in build_plan.py if the real team is different."),
    ("Dates", f"Scheduled for the lanes above, Monday to Friday, skipping these holidays: {hol}. Each estimate carries a 20% buffer, each dependency leaves one clear day for review, and each milestone adds one week before it is called. Dates are fixed text; re-run qos/evidence/build_plan.py to reschedule."),
    ("Waves", "Wave 1 = Build in MVP, wave 2 = Build in Pilot, wave 3 = Build in GA. Every wave 2 item depends on VER-1 and every wave 3 item on VER-2, so a later wave never starts before the earlier gate closes."),
    ("Freeze", "The plan does not override docs/FREEZE_SCOPE.md. Live NIC e-way, GSTR-2B API, Tally and WhatsApp Cloud stay behind their flags, default off, and are built against fakes and offline inputs. Flipping a flag is a separate freeze exception."),
    ("What you edit", "Only the cream cells: Owner, the five stage cells, Actual start, Actual done, Blocked reason, PR / branch and Evidence."),
    ("Stage values", "Not started, In progress, Done, Blocked, N/A. Use N/A when a stage does not apply."),
    ("Definition of done", "An item is Done when all five stages are Done or N/A. What each stage means depends on the item's Kind (column AG): see the Acceptance criteria column, which states the item's own pass condition, its rejecting case and the done rule for its kind. Features: tests for the touched apps on Postgres, lint and types clean, register_sync scores the test. Web: Vitest or Playwright, tsc -b, ESLint, accessibility check. Performance: benchmark job report. Drill: recorded timings. Decision and external: recorded decision or written sign-off. Gate: checklist."),
    ("Reviewer rule", "The author never signs their own Review. Agent-built work gets an agent code-review pass, then the human signs. Human-built work gets an agent review, then the human signs after a day. Compliance items also need the CA; pharmacy items a licensed pharmacist."),
    ("When tests run", "Each pull request: tests for the touched apps plus lint and type checks. Full backend suite on Postgres: nightly and at each verification gate. Performance and load tests: their own scheduled job, never in the pull-request run."),
    ("Source of truth", "Bizboard_Product_Task_Universe_Master.xlsx is the source of truth and the file register_sync.py updates. Bizboard_Master_Task_Register_Enhanced.xlsx is a mirror written by recalc_xlsx.ps1 -Mirror. Archives are read-only."),
    ("Other plans", "Production bugs jump the queue, capped at 20% of capacity, and each interrupt is logged in Plan change log. This plan preempts the bug-remediation, UX, FMEA and ISO 25010 plans for new work; items there that duplicate a work item here are merged into it."),
    ("Slips", "An item more than 2 working days late triggers a re-plan. Every wave 1 item has a cut-line rank in column AH: rank 1 moves to wave 2 first. Before each wave starts, re-check its estimates with a one-day spike."),
    ("RAG", "Done when finished. Red when Blocked or past the planned due date. Amber when started, due within 3 days and under 50 percent complete. Otherwise Green."),
    ("Register columns", "'Register work status' and 'Register verification' are live lookups of the Task Register, so the plan and the register cannot disagree about whether a task is verified."),
    ("Weekly routine", "Monday: set stages and actual dates, record blockers, rerun register_sync.py after a test run, recalculate the workbook (qos/tools/recalc_xlsx.ps1), review Plan rollup and Plan by week, and log any date or scope change in Plan change log."),
]
guide.column_dimensions["A"].width = 26
guide.column_dimensions["B"].width = 120
for r, (k, v) in enumerate(text, 10):
    a = guide.cell(r, 1, k)
    a.font, a.alignment = Font(name=FONT, size=10, bold=True), wrap
    b = guide.cell(r, 2, v)
    b.font, b.alignment = body, wrap
    guide.row_dimensions[r].height = max(30, 14 * math.ceil(len(v) / 120) + 4)
guide.row_dimensions[2].height = 30
guide.merge_cells("A2:B2")
BUF = "'Plan guide'!$B$6"

# ---- Plan decisions
title(dec, "Plan decisions: the 63 pre-implementation questions", "Status: Decided = settled here; Confirm = default chosen, founder confirms before the item starts; External = needs a CA, pharmacist, host or other outside input; Dropped = removed from the plan.")
header(dec, 4, ["Q", "Topic", "Items", "Status", "Answer", "What changed in the plan", "Founder confirmed (date)"], [5, 28, 18, 11, 100, 40, 16])
for n, (q, topic, its, status, ans, chg) in enumerate(QA):
    r = 5 + n
    for c, v in enumerate([q, topic, its, status, ans, chg, None], 1):
        cell = dec.cell(r, c, v)
        cell.font, cell.alignment, cell.border = body, wrap, box
    dec.cell(r, 7).fill = inp
    dec.row_dimensions[r].height = max(30, 13 * math.ceil(len(ans) / 105) + 4)
dec.freeze_panes = "C5"
dec.auto_filter.ref = f"A4:G{4 + len(QA)}"
for txt, color in (("Decided", "FFC6EFCE"), ("Confirm", "FFFFEB9C"), ("External", "FFFFE0B2"), ("Dropped", "FFD9D9D9")):
    dec.conditional_formatting.add(f"D5:D{4 + len(QA)}", CellIsRule(operator="equal", formula=[f'"{txt}"'], fill=fill(color)))

# ---- Implementation plan
cols = ["WI ID", "Register task", "Work item", "Wave", "Release gate", "Workstream", "Layer", "Scope (quality-first)", "Acceptance criteria",
        "Planned test file", "Depends on", "Owner", "Estimate (days)", "Planned days (with buffer)", "Planned start", "Planned due",
        "Design", "Build", "Tests", "Review", "Register sync", "Status", "% done", "Actual start", "Actual done", "Days late", "RAG",
        "Blocked reason", "PR / branch", "Evidence (test ids, run id)", "Register work status", "Register verification", "Kind",
        "Cut line", "Decision refs (Q)", "Plan key"]
widths = [9, 11, 38, 6, 9, 20, 12, 52, 66, 40, 14, 11, 9, 10, 12, 12, 11, 11, 11, 11, 11, 12, 8, 12, 12, 8, 8, 24, 24, 28, 18, 14, 11, 9, 11, 11]
title(plan, "Implementation plan", "One row per work item. Cream cells are inputs; everything else is a formula or fixed plan text. Filter on Wave, Owner, Status, RAG or Kind.")
header(plan, 4, cols, widths)
plan.row_dimensions[4].height = 32
F0 = 5
LAST = F0 + len(items) - 1
ref = lambda col: f"'Implementation plan'!${col}${F0}:${col}${LAST}"
STAGES = ["Design", "Build", "Tests", "Review", "Register sync"]
dv = DataValidation(type="list", formula1='"Not started,In progress,Done,Blocked,N/A"', allow_blank=False)
dvo = DataValidation(type="list", formula1='"' + ",".join(OWNERS) + '"', allow_blank=True)
plan.add_data_validation(dv)
plan.add_data_validation(dvo)
for n, i in enumerate(items):
    r = F0 + n
    k, t, kind = i["key"], i["task"], i["kind"]
    slug = (t or k).lower().replace("-", "_")
    if kind in ("gate", "decision", "external"):
        test = ""
    elif kind == "perf":
        test = "backend/perf/test_" + slug + "_benchmark.py (nightly job)"
    elif kind == "infra drill":
        test = "drill log in qos/evidence/ (restore or alert drill)"
    elif kind == "tooling":
        test = "qos/tools/tests/test_register_sync_web.py"
    elif i["layer"].startswith("Web"):
        test = f"web/src/__tests__/{slug}.test.tsx"
    else:
        test = f"backend/tests/test_plan_{slug}.py"
    test = {"CUST-LOCK": "backend/tests/test_register_race_gaps.py; backend/tests/test_plan_cust_lock.py",
            "P-0115": "backend/tests/test_register_audit_coverage.py", "X-0432": "backend/tests/test_register_audit_coverage.py",
            "SEC-0624": "backend/tests/test_mfa.py; backend/tests/test_mfa_mandatory.py; backend/tests/test_register_integrity_gaps.py (xfail test)",
            "S-0561": "backend/tests/test_plan_s_0561.py; backend/tests/test_register_integrity_gaps.py (invariant tests)"}.get(k, test)
    passed, rej = PASS.get(k, (i["scope"], TEMPLATE_REJECT["web" if kind == "web" else "feature"]))
    crit = f"Pass: {passed}. Rejecting case: {rej}. Done means: {DOD[kind if kind in DOD else 'feature']}."
    zero = i["days"] == 0
    vals = [i["id"], t, i["title"], i["wave"], GATE[i["wave"]], i["ws"], i["layer"], i["scope"], crit, test,
            ", ".join(by_key[d]["id"] for d in i["deps"]), i["owner"], i["days"], f"=ROUNDUP(M{r}*(1+{BUF}),0)", i["start"], i["due"]]
    for c, v in enumerate(vals, 1):
        cell = plan.cell(r, c, v)
        cell.font, cell.alignment, cell.border = body, wrap, box
    na = set()
    if zero:
        na = {0, 1, 2}
    if kind in ("decision", "external"):
        na = {1, 2, 4}
    if kind == "gate":
        na = {0, 1}
    for kk in range(5):
        c = plan.cell(r, 17 + kk, "N/A" if kk in na else "Not started")
        c.font, c.fill, c.border, c.alignment = body, inp, box, Alignment(horizontal="center", vertical="top")
        dv.add(c)
    plan.cell(r, 12).fill = inp
    dvo.add(plan.cell(r, 12))
    st = f"Q{r}:U{r}"
    plan.cell(r, 22, f'=IF(COUNTIF({st},"Blocked")>0,"Blocked",IF(COUNTIF({st},"Done")+COUNTIF({st},"N/A")=5,"Done",'
                     f'IF(COUNTIF({st},"Done")+COUNTIF({st},"In progress")>0,"In progress","Not started")))')
    plan.cell(r, 23, f'=IF(5-COUNTIF({st},"N/A")=0,1,COUNTIF({st},"Done")/(5-COUNTIF({st},"N/A")))')
    for c in (24, 25, 28, 29, 30):
        plan.cell(r, c).fill = inp
    plan.cell(r, 26, f'=IF(V{r}="Done",IF(Y{r}="",0,MAX(0,Y{r}-P{r})),MAX(0,TODAY()-P{r}))')
    plan.cell(r, 27, f'=IF(V{r}="Done","Done",IF(V{r}="Blocked","Red",IF(Z{r}>0,"Red",'
                     f'IF(AND(O{r}<=TODAY(),P{r}-TODAY()<=3,W{r}<0.5),"Amber","Green"))))')
    if t:
        wscol, vcol = L(head["Work status"]), L(head["Verification result"])
        plan.cell(r, 31, f"=IFERROR(INDEX('Task Register'!${wscol}$2:${wscol}${tr.max_row},MATCH(B{r},'Task Register'!$A$2:$A${tr.max_row},0)),\"\")")
        plan.cell(r, 32, f"=IFERROR(INDEX('Task Register'!${vcol}$2:${vcol}${tr.max_row},MATCH(B{r},'Task Register'!$A$2:$A${tr.max_row},0)),\"\")")
    plan.cell(r, 33, kind)
    plan.cell(r, 34, CUT.get(k, "") if i["wave"] == 1 and kind not in ("gate", "decision", "external") else "")
    plan.cell(r, 35, QREF.get(k, ""))
    plan.cell(r, 36, k)
    for c in range(22, 37):
        if c in (24, 25, 28, 29, 30):
            continue
        plan.cell(r, c).font = body
        plan.cell(r, c).border = box
        plan.cell(r, c).alignment = Alignment(vertical="top", horizontal="center", wrap_text=True)
    for c in (15, 16, 24, 25):
        plan.cell(r, c).number_format = "dd-mmm-yy"
    plan.cell(r, 23).number_format = "0%"
    plan.row_dimensions[r].height = 118
plan.freeze_panes = "D5"
plan.auto_filter.ref = f"A4:{L(len(cols))}{LAST}"
rng = lambda c: f"{c}{F0}:{c}{LAST}"
for txt, color in (("Done", "FFC6EFCE"), ("Blocked", "FFFFC7CE"), ("In progress", "FFFFEB9C")):
    for c in ("V", "Q", "R", "S", "T", "U"):
        plan.conditional_formatting.add(rng(c), CellIsRule(operator="equal", formula=[f'"{txt}"'], fill=fill(color)))
for txt, color in (("Green", "FFC6EFCE"), ("Done", "FFC6EFCE"), ("Amber", "FFFFEB9C"), ("Red", "FFFFC7CE")):
    plan.conditional_formatting.add(rng("AA"), CellIsRule(operator="equal", formula=[f'"{txt}"'], fill=fill(color)))

# ---- Plan rollup
title(roll, "Plan rollup", "Live counts from the Implementation plan sheet. Effort % weights by estimate days.")


def block(r0, label, keycol, keys):
    header(roll, r0, [label, "Items", "Done", "In progress", "Blocked", "Red", "Estimate days", "Days done", "Effort done %", "Item done %"],
           [26, 9, 9, 11, 9, 9, 13, 11, 13, 12])
    for k, key in enumerate(keys, 1):
        r = r0 + k
        crit = key if isinstance(key, int) else f'"{key}"'
        roll.cell(r, 1, key if not isinstance(key, int) else f"Wave {key}: {GATE[key]}")
        roll.cell(r, 2, f"=COUNTIF({ref(keycol)},{crit})")
        roll.cell(r, 3, f'=COUNTIFS({ref(keycol)},{crit},{ref("V")},"Done")')
        roll.cell(r, 4, f'=COUNTIFS({ref(keycol)},{crit},{ref("V")},"In progress")')
        roll.cell(r, 5, f'=COUNTIFS({ref(keycol)},{crit},{ref("V")},"Blocked")')
        roll.cell(r, 6, f'=COUNTIFS({ref(keycol)},{crit},{ref("AA")},"Red")')
        roll.cell(r, 7, f"=SUMIFS({ref('M')},{ref(keycol)},{crit})")
        roll.cell(r, 8, f"=SUMPRODUCT(({ref(keycol)}={crit})*{ref('M')}*{ref('W')})")
        roll.cell(r, 9, f"=IF(G{r}=0,0,H{r}/G{r})")
        roll.cell(r, 10, f"=IF(B{r}=0,0,C{r}/B{r})")
        for c in range(1, 11):
            roll.cell(r, c).font, roll.cell(r, c).border = body, box
        roll.cell(r, 9).number_format = roll.cell(r, 10).number_format = "0%"
        roll.cell(r, 8).number_format = roll.cell(r, 7).number_format = "0.0"
    r = r0 + len(keys) + 1
    roll.cell(r, 1, "Total").font = Font(name=FONT, size=10, bold=True)
    for c in range(2, 9):
        roll.cell(r, c, f"=SUM({L(c)}{r0 + 1}:{L(c)}{r - 1})").font = Font(name=FONT, size=10, bold=True)
    roll.cell(r, 9, f"=IF(G{r}=0,0,H{r}/G{r})").number_format = "0%"
    roll.cell(r, 10, f"=IF(B{r}=0,0,C{r}/B{r})").number_format = "0%"
    return r + 2


r = 4
r = block(r, "Wave", "D", [1, 2, 3])
r = block(r, "Workstream", "F", [AUD, SEC, GST, PAY, INV, PLT, GRO, QG])
r = block(r, "Owner", "L", OWNERS)
r = block(r, "Kind", "AG", ["feature", "web", "perf", "infra drill", "tooling", "decision", "external", "gate"])
roll.column_dimensions["A"].width = 26

# ---- Plan by week
last_due = max(i["due"] for i in items)
weeks, w = [], START
while w <= last_due + timedelta(days=14):
    weeks.append(w)
    w += timedelta(days=7)
title(week, "Plan by week", "Planned vs actual completion by week. Actual uses the Actual done date you enter on the plan.")
header(week, 4, ["Week start", "Week end", "Items due", "Planned days due", "Items done (actual)", "Cumulative planned items", "Cumulative done items",
                 "Planned % complete", "Actual % complete", "Gap (items)"], [14, 14, 11, 14, 14, 16, 16, 14, 14, 11])
total = f"COUNTA({ref('A')})"
for k, ws_ in enumerate(weeks):
    r = 5 + k
    week.cell(r, 1, ws_)
    week.cell(r, 2, f"=A{r}+6")
    week.cell(r, 3, f'=COUNTIFS({ref("P")},">="&A{r},{ref("P")},"<="&B{r})')
    week.cell(r, 4, f'=SUMIFS({ref("N")},{ref("P")},">="&A{r},{ref("P")},"<="&B{r})')
    week.cell(r, 5, f'=COUNTIFS({ref("Y")},">="&A{r},{ref("Y")},"<="&B{r})')
    week.cell(r, 6, f"=SUM(C$5:C{r})")
    week.cell(r, 7, f'=IF(A{r}>TODAY(),"",SUM(E$5:E{r}))')
    week.cell(r, 8, f"=F{r}/{total}")
    week.cell(r, 9, f'=IF(G{r}="","",G{r}/{total})')
    week.cell(r, 10, f'=IF(G{r}="","",F{r}-G{r})')
    for c in range(1, 11):
        week.cell(r, c).font, week.cell(r, c).border = body, box
    week.cell(r, 1).number_format = week.cell(r, 2).number_format = "dd-mmm-yy"
    week.cell(r, 8).number_format = week.cell(r, 9).number_format = "0%"
week.freeze_panes = "A5"

# ---- Milestones
title(mile, "Plan milestones", "A milestone is Ready only when every item in its wave, including its verification item, is Done. The planned date is the last due date plus one release-buffer week.")
header(mile, 4, ["Milestone", "Wave", "Planned date", "Items not Done", "Status", "Exit criteria"], [30, 7, 14, 14, 16, 100])
exits = {
    1: "All wave 1 items Done: audit events on every posting action, mandatory admin 2FA, field masking, encryption, ITC and e-way rules (stub actions, flags off), approval queue, credit controls, nightly trial-balance worker, restore drill. Full suite green on Postgres; drift check clean; register shows Built - tested for each. CA sign-off of the Rule 11(g) map: if missing, ship as 'pilot with documented residual'.",
    2: "All wave 2 items Done: pilot-breadth features and POS polish verified; end-to-end tests for complaints, lead de-duplication and signup; no open Red items; 0 Fail results in the register for Pilot rows.",
    3: "All wave 3 items Done: differentiators built and verified (Tally and GSTR-2B features still behind their flags); no unreviewed Mechanism not found on P1 compliance rows.",
}
for k, wv in enumerate((1, 2, 3)):
    r = 5 + k
    mile.cell(r, 1, f"M{wv}: {GATE[wv]} gate ready")
    mile.cell(r, 2, wv)
    mile.cell(r, 3, f"=SUMPRODUCT(MAX(({ref('D')}=B{r})*{ref('P')}))+7")
    mile.cell(r, 4, f'=COUNTIFS({ref("D")},B{r},{ref("V")},"<>Done")')
    mile.cell(r, 5, f'=IF(D{r}=0,"Ready","Open")')
    mile.cell(r, 6, exits[wv])
    for c in range(1, 7):
        mile.cell(r, c).font, mile.cell(r, c).border, mile.cell(r, c).alignment = body, box, wrap
    mile.cell(r, 3).number_format = "dd-mmm-yy"
    mile.row_dimensions[r].height = 76
mile.conditional_formatting.add("E5:E7", CellIsRule(operator="equal", formula=['"Ready"'], fill=fill("FFC6EFCE")))
mile.cell(9, 1, "Open confirmations before the first affected item starts").font = Font(name=FONT, size=11, bold=True)
mile.cell(10, 1, "Decisions marked Confirm or External").font = body
mile.cell(10, 4, "=COUNTIF('Plan decisions'!D5:D67,\"Confirm\")+COUNTIF('Plan decisions'!D5:D67,\"External\")").font = body
mile.cell(11, 1, "...of which not yet confirmed (no date)").font = body
mile.cell(11, 4, "=COUNTIFS('Plan decisions'!D5:D67,\"Confirm\",'Plan decisions'!G5:G67,\"\")+COUNTIFS('Plan decisions'!D5:D67,\"External\",'Plan decisions'!G5:G67,\"\")").font = body

# ---- change log
title(log, "Plan change log", "Record every change to dates, scope or estimates here so the plan stays auditable.")
header(log, 4, ["Date", "Change", "Items affected", "Reason", "Changed by"], [12, 70, 24, 60, 22])
entries = [
    (date(2026, 10, 4), "Plan created from the quality-first decisions.", "All", "67 items, 197 estimate days, 3 developers.", "Claude (delegated)"),
    (date(2026, 10, 4), "Plan revised after the 63 pre-implementation questions: 2 agent lanes, start 12 Oct, holidays, review gap, wave gates enforced, per-item pass conditions, freeze-safe scopes, estimates for WI-010, 028, 044, 050 and 061 changed, WI-028 split, WI-062, 063, 065, 066 dropped, new items REG-WEB, DEC-HOST, DEC-CA, CA-SIGN, WI-028b.",
     "All", f"{len(items)} items, {sum(i['days'] for i in items):g} estimate days.", "Claude (delegated)"),
    (date(2026, 10, 4), "Repo check folded in: MFA roles, existing credit hold, seal alert channel, Cashfree/PayU for subscription invoices, and no cart timeout. UX-0582 now depends on S-0562. Q21 and Q51 moved to Decided.",
     "WI-010, WI-021, WI-034, WI-046, WI-051, WI-053", "Code read for the items previously marked verify at item start.", "Agent"),
]
for n, e in enumerate(entries):
    for c, v in enumerate(e, 1):
        cell = log.cell(5 + n, c, v)
        cell.font, cell.border, cell.alignment = body, box, wrap
    log.cell(5 + n, 1).number_format = "dd-mmm-yy"
    log.row_dimensions[5 + n].height = 60

# dropped tasks: say so in the register
for t, q in DROPPED.items():
    old = tr.cell(rows[t], head["Notes"]).value
    note = f"Plan 2026-10-04 (Q{q}): dropped from the implementation plan; On request, pending CA confirmation."
    if not old or note not in str(old):
        tr.cell(rows[t], head["Notes"], (str(old) + " | " if old else "") + note)

wb.save(sys.argv[1])
print(f"items {len(items)}  est days {sum(i['days'] for i in items):g}  planned days {sum(i['planned'] for i in items)}")
for wv in (1, 2, 3):
    print(f"wave {wv}: {sum(1 for i in items if i['wave'] == wv)} items, ends {max(i['due'] for i in items if i['wave'] == wv)}")
