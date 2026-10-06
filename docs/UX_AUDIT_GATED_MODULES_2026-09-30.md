# UX audit of the flag-gated modules (original audit prompt, run on the remaining features)

Date 2026-09-30. Scope: the 59 routes that the first audit could not see because their module flag was off (`docs/UX_FEATURE_PHASES.md`). Findings are in `docs/ux/L2_finding_ledger.csv` (UX-M01..M20). The build plan is `docs/roadmap/GATED_MODULES_DETAILED_IMPLEMENTATION_PLAN.md`.

## How this was measured (and what was not)

| Method | Coverage |
|---|---|
| Real backend, audit company "UX Audit Traders" (all modules on, six-month draft history seeded), Chrome | 141-route crawl at desktop and 393px: axe WCAG 2.2 AA, touch targets, h1, overflow, console errors, render time |
| Scripted read-only walk (`e2e/ux-module-walk.spec.ts`) | All 59 gated routes: headings, buttons, tables, alerts, page text, and the first create action. Nothing was submitted |
| Static scan (`scripts/ux_static_scan.py`) | Control counts, hard-coded strings, loading/error/empty presence |
| Roles | Owner for all routes; policy-desk user for insurance. Accountant, CA, inventory and sales users exist but were **not** walked |
| **Not done** | Dark mode (theme is light only), Lighthouse or real-data timings, Hindi walk of every screen (Hindi checked by string parity only), user sessions, posting or reversing real documents, AI screens (consent is off on purpose because the dev API holds live LLM keys) |

Route coverage after this pass: 54 of 59 audited on the real backend, 5 insights routes audited only at the consent gate. Console errors on load: 0 of 141 routes.

## 1. Executive UX audit

**Overall.** The gated modules are in better shape than a "hidden, unfinished" label suggests. There are no serious accessibility failures beyond three small ones (now fixed), no horizontal overflow at 393px, average render about 1.1s on real data, and the honesty copy the Holistic plan asked for is already on the screens. The problems are of three kinds: developer language and raw enums in user-facing text, growth and service screens that lead with an always-open create form, and a few states that contradict themselves (books on with no chart of accounts; three GST return pages that are stubs).

### Top 10 findings

| # | Finding | Sev | Ledger |
|---|---|---|---|
| 1 | Books screens contradict each other when books are on but the chart is missing: "No accounts, enable accounting", totals 0.00 yet "does not tie", same banner on four screens | High | UX-M01 |
| 2 | GSTR-6/7/8 pages are stubs with the disclaimer in the H1, and appear in the menu when the extended flag is on | High | UX-M02 |
| 3 | Complaints, tickets, job cards, projects, contracts, campaigns and referrals open with a full create form, pushing the list below the fold (9 to 13 fields before any record) | High | UX-M07 |
| 4 | Leads is the busiest growth screen (55 controls) and mixes daily work with capture setup (webhook links, CSV import) | High | UX-M08 |
| 5 | Unnamed controls: lead assignee selects (8), progress bars on the dashboard checklist, setup wizard and insights | High | UX-M09, M10 (fixed) |
| 6 | Nine subtitles used developer words (API name, TRANSFER_OUT, track_serial, SLM, CoA, contra, back-fill, curator) | Medium | UX-M04 (fixed) |
| 7 | Raw enum values in lists and forms (OTHER, MEDIUM, IN_PROGRESS, WARRANTY, FLAT, DIGITAL, MOTOR) | Medium | UX-M05 |
| 8 | Resolution time shown in seconds | Medium | UX-M06 |
| 9 | Two routes are the same page (CA needs, Missing documents) | Medium | UX-M03 |
| 10 | Billing shows "Start checkout" next to "Checkout stays closed" | Medium | UX-M14 |

**What is good, keep it.** "Not filed, worksheet for your CA" on every GST page; "does not send messages" on campaigns; "paid drafts a credit note, does not send cash" on referrals; "does not issue a policy" on insurance; "internal queue" on tickets; "not live Tally sync"; "No live payment connection" on the gateway page. Empty states are consistent ("Nothing here yet" plus a reason).

## 2. Frameworks applied to the remaining features

### 2.1 Jobs to be done

| Persona | Job (hypothesis until user sessions) | Modules |
|---|---|---|
| P1 owner | "When a customer owes me or has gone quiet, I want to see who and what to do, so cash comes in and they come back" | Collections, Customer 360, CRM, referrals, portal |
| P1 owner | "When something goes wrong after a sale, I want it recorded and fixed without losing the customer" | Complaints, tickets, credit notes |
| P1 owner | "When a warranty or AMC ends, I want to know before it does" | Contracts, Attention |
| P5 bookkeeper / P6 CA | "When the month ends, I want books that tie and returns I can hand over" | Books, periods, GST worksheets, missing documents |
| P4 store keeper | "When goods move or expire, I want the stock to say so" | Godowns, transfers, serials, expiry, fixed assets |
| P3 field seller | "When I meet a prospect, I want to log the lead and follow up on my phone" | Leads, opportunities, pipeline |
| ARCH-07 service firm | "When I do a job or a project milestone, I want it billed" | Job cards, projects, contracts |
| ARCH-03 maker / employer | "When I make goods or pay staff, I want it recorded without a second system" | Manufacturing, payroll |

### 2.2 Journeys (new: J11 to J13)

| Journey | Steps | Where friction was seen |
|---|---|---|
| **J11 Grow: lead to cash** | Capture lead, dedupe, assign, qualify, opportunity, quotation, order, invoice, receipt | Leads screen mixes setup with daily work (M08); copy says "not a CRM pipeline" while a Pipeline page exists (M11); enums raw (M05) |
| **J12 Keep: after-sales** | Complaint or ticket, assign, inspect or resolve, credit note or renewal | Create form always open (M07); resolution in seconds (M06); raw statuses (M05) |
| **J13 Make and pay** | BOM, work order, release, produce; employee, pay run | Release failure is described, not prevented (M13); both start on an empty page with one Add button |
| J9 (extended) Close the month | Books on, chart, journals, period, reports, GST worksheets, CA handoff | M01, M02, M03 |

### 2.3 Task analysis (measured on the real backend, no submits)

| Task | Screens | Visible fields before the first record | Note |
|---|---|---|---|
| Create a complaint | 1 (inline form) | 3 (customer, category, description) | Short form, but always open |
| Create a ticket | 1 | 3 plus assignee filter | Same |
| Add a contract | 1 | 7 plus a line table | Longest of the service forms |
| Add a lead | Leads, Add | 21 inputs on the page (filters, import, links) | Load is the page, not the form |
| Issue a referral code | 1 | 3 | Fine |
| Create a campaign | 1 | 9 (all optional except name) | Optional fields shown at once |
| Payroll: add employee, run pay | 2 | Not walked past the list | Needs a posted-document walk |
| Bank reconciliation | 2 | 10 inputs before a statement exists | Needs a statement; blocked message is clear |

### 2.4 Heuristic evaluation (0 good to 4 bad)

| Heuristic | Growth and service | Books and GST | Inventory depth | Ops and settings |
|---|---|---|---|---|
| 1 Visibility of status | 1 | 2 (books banner) | 1 | 1 |
| 2 Match with real world | 3 (raw enums) | 2 | 3 (developer subtitles, now fixed) | 2 |
| 3 User control and freedom | 1 | 1 | 1 | 2 (release fails) |
| 4 Consistency | 2 (inline forms vs dialogs) | 1 | 1 | 1 |
| 5 Error prevention | 2 | 1 | 1 | 3 (release, checkout) |
| 6 Recognition over recall | 2 | 2 | 1 | 2 |
| 7 Flexibility and efficiency | 2 | 1 | 1 | 1 |
| 8 Minimal design | 3 (Leads, campaigns) | 2 | 1 | 2 |
| 9 Help with errors | 2 (error states unconfirmed) | 1 | 2 | 2 |
| 10 Help and documentation | 1 (honesty copy present) | 1 | 1 | 1 |

### 2.5 Cognitive walkthrough

| Task | Will the user know what to do | See the control | Connect it to the goal | Understand the feedback |
|---|---|---|---|---|
| Report a complaint from a customer call | Yes | Yes, but it is a form with no verb ("Create") | Category "OTHER" is uppercase and unexplained | Unknown, not submitted |
| Move a deal to Won | Pipeline explains drag and drop | Yes (Kanban) | Yes | Not walked |
| Find who to chase for money | Collections and Customer 360 exist | Two entry points | Fine | Unknown |
| Close the month | Periods page says soft-close warns and closed blocks | Yes | Blocked by the books banner if the chart is missing (M01) | Yes |
| Read GSTR-6 | Page is a stub | Menu shows it | No | The stub says nothing is calculated (now plain) |

### 2.6 Cognitive load (static score 1 to 5 over the gated pages)

Highest: Leads 55 controls (4), Complaints 35 (3), GSTR-2B 32 (3), Supplier complaints 32 (3), Tickets 30 (3), Expenses 28 (3), Work orders 27 (3), Contracts 26 (3), Insurance 25 (3). No gated page reaches 5. The first audit's five score-5 screens (Products, New invoice, New purchase, Item dialog, Invoice detail) remain the concentration.

### 2.7 HEART additions for the new modules

| Dimension | Metric | Source today |
|---|---|---|
| Adoption | Share of companies with at least one lead, complaint, ticket or contract; time from module grant to first record | Server-derivable |
| Engagement | Leads moved per week; tickets touched per week; renewals actioned | Server-derivable |
| Task success | Lead to won conversion and days; tickets resolved within SLA; contracts renewed vs expired; complaint to credit note time | Server-derivable |
| Happiness | CSAT after resolving a ticket or complaint (owner) | New event needed (allowed, GD-5) |
| Retention | Companies still using a granted module after 4 weeks | Server-derivable |

## 3. Screen-by-screen (all 59, grouped)

| Phase | Screens | Result on the real backend | Main issues |
|---|---|---|---|
| G1 Books and close (10) | Chart of accounts, journals, bank reconciliation, cost centres, periods, expenses, trial balance, P&L, balance sheet, books health | All render; axe clean | M01 books state; M04 jargon (fixed); reconciliation is blocked until a statement exists (message is clear) |
| G2 GST and compliance (14) | GSTR-1, 3B, 4, 6, 7, 8, 9, 2B, CMP-08, TDS/TCS, GST health, rate exposure, missing documents, CA needs | All render; axe clean | M02 stubs; M03 duplicate; honesty copy strong |
| G3 Inventory and statutory (7) | Warehouses, transfers, serials, expiry alerts, bills of entry, fixed assets, statutory licences | All render; empty states clear | M04 (fixed), M12 |
| G4 Growth (6) | Leads, CRM checklist, opportunities, campaigns, pipeline, referrals | Render after the plan fix; leads had axe failures (fixed) | M05, M07, M08, M09, M11 |
| G5 Service and contracts (8) | Complaints, supplier complaints, tickets, shared tickets, job cards, projects, insurance, contracts | Render; insurance needs the policy-desk role | M05, M06, M07, M15, M16 |
| G6 Operations (4) | BOMs, work orders, employees, pay runs | Render; employees show seeded rows | M13 |
| G7 Intelligence (5) | Insights hub, alerts, health, cashflow, assistant | Consent gate only | AI consent stays off; see plan |
| G8 Settings and integrations (5) | Payment gateway, billing, price lists, Telegram, Tally | Render; fail-closed copy present | M14 billing |

## 4. Fixed in this pass (uncommitted)

Unnamed progress bars (3 files); lead assignee selects; nine developer-worded subtitles in English and Hindi; the GSTR stub body copy; the demo tooling now seeds the chart of accounts and moves the audit company to a plan that names every module; the audit provisioning gained a policy-desk user. Backend tests: 11 pass.

## 5. Backlog, metrics, plan

Full ledger: `docs/ux/L2_finding_ledger.csv` (UX-M01..M20). Detailed build plan: `docs/roadmap/GATED_MODULES_DETAILED_IMPLEMENTATION_PLAN.md`.
