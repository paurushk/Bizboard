# Bizboard Data Protection Impact Assessment: first draft (WP-2, 2026-10-25)

**Status: draft for counsel. Not approved, not legal advice.** Written from the product as it
stands in the repository. Each control names the file or test that implements it. Rows BB-123 and
BB-047 in `docs/Bizboard_SaaS_Readiness_Checklist.xlsx` stay open until counsel signs §9.

Sources:
- `docs/ops/DATA_CATEGORIES.md`
- `docs/pilot/DPDP_POSTURE.md`
- `docs/ops/PRODUCT_BEHAVIORS_FOR_COUNSEL.md`
- `docs/ops/SUBPROCESSORS.md`
- `docs/ops/STRIDE.md`
- `docs/ops/DATA_RETENTION.md`
- `docs/ops/ERASURE_PLAYBOOK.md`
- `docs/ops/DPDP_REQUESTS.md`
- `docs/ops/INCIDENT_RESPONSE.md`
- the drafts beside this file (`PRIVACY_POLICY_DRAFT.md`, `DATA_PROCESSING_AGREEMENT_DRAFT.md`,
  `TERMS_OF_SERVICE_DRAFT.md`)

## 1. Is a DPIA legally required?

Under the Digital Personal Data Protection Act, 2023, a periodic DPIA and audit are duties of a
**Significant Data Fiduciary**, a status the Central Government notifies by class or by name
(volume and sensitivity of data, risk to people, and so on). Bizboard has not been notified.

Bizboard has two roles:
- **Data Fiduciary** for the people who use it: owners and staff accounts, sign-in data,
  subscription billing.
- **Data Processor** for the personal data inside each business's records: that business's
  customers, suppliers and employees. The business is the fiduciary for that data
  (`DATA_PROCESSING_AGREEMENT_DRAFT.md`).

**Question for counsel (Q1):** is a DPIA required now, or is this a voluntary assessment? We
recommend keeping it either way. It is the basis for the privacy policy, the DPA and the pentest
scope.

## 2. What is processed

| Category | Examples | Where stored | Whose data / role |
|---|---|---|---|
| Account identity | Owner and staff name, email, mobile, password hash, two-step secret (encrypted) | `accounts.User`, `accounts.CompanyUser`, `accounts.UserMfa` | Users: Bizboard is fiduciary |
| Sign-in and audit | Sign-in events, IP, device and session list, activity log | `accounts` sessions, `core.AuditEvent` | Users: fiduciary |
| Party records | Customer and supplier name, phone, email, GSTIN, address, optional location pin | `masters.Customer`, `masters.Supplier` | Business's contacts: processor |
| Money documents | Invoices, credit/debit notes, receipts, payments, GSTR worksheets | `sales`, `purchases`, `payments`, `reporting` | Mixed: processor |
| Employees (payroll, if used) | Name, pay, statutory ids | `payroll` (module off for freeze) | Business's employees: processor |
| Files | Invoice PDFs, bill photos, import files, exports | `core.FileAsset`, media storage | Processor |
| Messages | WhatsApp send status, dunning flags, email and SMS codes | `sales`, `payments`, `core.Notification` | Mixed |
| Telemetry | Shop-floor and help-search events, without GSTIN or phone | `insights`, help events | Users: fiduciary |
| SaaS billing | Plan, seats, Razorpay ids, Bizboard's own GST invoices, TDS claims | `billing` | Business as customer: fiduciary |
| Feedback | NPS/CSAT score and comment | `support.SatisfactionResponse` | Users: fiduciary |
| Bizboard referrals (if built, flag off) | Which business referred which (company ids only), sign-up and qualification dates | `billing.ReferralLink`, `billing.ReferralEvent`, `Company.referred_by` | Businesses: fiduciary |
| Trial abuse checks | Keyed one-way hashes of GSTIN, PAN, owner phone and email, kept after erasure | `billing` | Fiduciary |

**Not stored:** card numbers or CVV (`docs/ops/PCI_SCOPE.md`; payment pages are the gateway's).
Request bodies are not logged.

**Purposes:** run the service the business signed up for; keep tax records; secure sign-in;
billing; support (only with the owner's grant); product improvement from counts and events
without party PII. **Lawful basis:**
- for users: performance of the contract, plus legitimate uses under the DPDP Act s.7 (counsel to confirm, Q2);
- for party data: the business's own basis, with Bizboard acting on its instructions.

## 3. Who can see the data

| Who | What | Control |
|---|---|---|
| Users of the same company | By role (Owner, Manager, Sales staff, Inventory staff, Accountant, Auditor, Viewer) | Role permissions; owner-only user and billing screens |
| Users of another company | Nothing | Every row carries `company_id`; Postgres row-level security is enforced, and production and staging refuse to start with it off (`_assert_postgres_rls_required` in `backend/config/settings.py`); the app connects as a role that cannot bypass it (`scripts/sql/app_role.sql`). Cross-tenant ids return 404 (`backend/tests/tenancy/`; live probe `scripts/security/tenant_probe.py`) |
| Bizboard support staff | Read-only, one request, up to 72 hours, only when the Owner grants it; every page viewed is logged and shown to the Owner | `support.SupportAccessGrant`; no impersonation route (`guard_no_impersonation`) |
| Bizboard operators | Production database and backups | Break-glass access logged; Django admin off unless enabled (`ADMIN_ENABLED`); admin is superuser-only |
| Sub-processors | Only what each needs (§4) | Contracts (`VENDOR_CONTRACT_CHECKLIST.md`) |

## 4. Where data goes (flows)

1. Browser or Android app → HTTPS edge (Cloudflare, if used) → nginx → Django API → PostgreSQL,
   Redis (cache and queues, no long-term personal data) and file storage.
2. Nightly encrypted backups → a separate off-host bucket (the backup job refuses to write an
   unencrypted copy in production).
3. Out to sub-processors, only when the feature is on:

   | Sub-processor | Receives | When |
   |---|---|---|
   | Email provider | Email address, message text | Codes, resets, alerts, retention warnings |
   | SMS provider | Mobile number, one-time code | OTP sign-in |
   | Razorpay | Subscriber name, email, phone, amount | Subscription billing |
   | Google | Nothing sent; Google returns email and name | "Sign in with Google" |
   | Cloudflare | IP, request traffic | Edge and Turnstile bot check |
   | AI provider (OpenAI by default; Anthropic or DeepSeek configurable) | Bill image, or question text with business figures | Only when the Owner switches AI on, and after a per-device consent for bill photos |
   | Telegram | Chat id, alert text | Only if a user links Telegram |
   | Meta WhatsApp Cloud | Customer phone, invoice message | Off; needs the customer's opt-in |
   | Payment gateways for the business's own customers | What the paying customer enters | Sandbox only today |

   Error reports go to **self-hosted** GlitchTip (not a sub-processor), with personal data
   scrubbed and IPs dropped (`docs/ops/GLITCHTIP.md`).

4. **Location:** depends on the host region, which is not chosen yet (D-18). India is
   recommended. AI providers may process outside India (Q3).

## 5. Risks and controls

Likelihood (L) and impact (I): 1 low to 3 high. "Remaining" is after the controls.

| # | Risk | L | I | Controls in place | Remaining | Further action |
|---|---|---|---|---|---|---|
| R1 | One business sees another's records | 2 | 3 | RLS enforced plus app checks (§3); tenancy test suites; live cross-tenant probe; erasure model coverage guard | Low | Independent pentest on hosted staging (BB-045/BB-144) |
| R2 | Account takeover | 2 | 3 | Hashed passwords, 10-character minimum; lockout and throttles; two-step sign-in required for Owner, Accountant and journal roles in production; sessions list and revoke; cookie-only sessions with CSRF on staging and production (BB-000547) | Low–medium | SMS DLT and email SPF/DKIM so codes reach users (BB-036/BB-037) |
| R3 | Insider or support misuse | 1 | 3 | Owner-granted, time-boxed, read-only support access with a viewed-page log; no impersonation; append-only activity log | Low | Named operator list and access review (`docs/ops/ACCESS_REVIEW.md`) |
| R4 | Backup or disk theft | 1 | 3 | Encrypted backups, separate account; two-step secrets and gateway keys encrypted in the database | Low | Confirm disk encryption at the host (Q4) |
| R5 | Keeping data too long | 2 | 2 | Read-only workspaces deleted after the owner's period (default 90 days, D-13), warned 30 and 7 days ahead; erasure on request; tombstone keeps only anonymised tax documents for 8 years; log retention 180 days | Low | Counsel confirms periods, then `DATA_RETENTION_ENFORCE=1` |
| R6 | Personal data in error reports or logs | 2 | 2 | Logs omit bodies and mask ids, document numbers, tokens, emails, phones, PAN, Aadhaar; GlitchTip scrubbing; browser relay only to our DSN | Low | — |
| R7 | AI provider sees business data | 2 | 2 | Off by default; Owner-only switch, logged; per-device consent for bill photos; agent steps kept 180 days | Medium | Provider DPA with no training on customer data and a stated region (Q3) |
| R8 | Data leaves India | 2 | 2 | Host region not chosen; AI optional | Medium | Choose an Indian region (D-18); disclose AI transfers |
| R9 | Unwanted messages to a business's customers | 1 | 2 | WhatsApp Cloud needs per-customer opt-in (default off, module off); dunning needs the Owner's switch and respects opt-out | Low | — |
| R10 | Breach not reported in time | 2 | 3 | Incident runbook with CERT-In 6-hour clock (`docs/ops/INCIDENT_RESPONSE.md`); alerting to founder email and phone; tabletop and game day (`docs/ops/TABLETOP_EXERCISES.md`, WP-6) | Medium | A named backup on call; counsel-approved notice templates |
| R11 | Children's data | 1 | 2 | B2B service for adults | Low | Payroll with a minor employee (Q5) |
| R12 | Offline drafts on a lost phone | 2 | 1 | Drafts only; screen-lock advice | Low | Consider encrypting offline storage |
| R13 | Referral data shows who uses Bizboard | 1 | 1 | Referrer sees counts only, never the referred business's name; flag off (D-19) | Low | One line in the privacy policy |

## 6. Rights of data principals

Process in `docs/ops/DPDP_REQUESTS.md`:
- access, correction, erasure (`erase_company`, tombstone mode), consent withdrawal and nomination;
- grievance, with escalation to the Data Protection Board;
- owners can export at any time;
- requests about a business's contacts go to that business, and we tell the requester.

Response time is to be confirmed against the DPDP Rules (Q6).

## 7. Breach response

`docs/ops/INCIDENT_RESPONSE.md`:
- severity is declared at once;
- CERT-In is reported within 6 hours where its Directions apply;
- the Data Protection Board and affected people are told as the Act and Rules require;
- where Bizboard is a processor, the business is told so it can tell its people;
- evidence is preserved and a postmortem is written within 3 business days.

## 8. Questions for counsel

1. Q1: Is a DPIA mandatory for Bizboard now (Significant Data Fiduciary status)?
2. Q2: Lawful basis for each user-data purpose (contract vs. legitimate uses).
3. Q3: The AI provider's terms (no training, retention, region), and how to disclose a transfer outside India.
4. Q4: Disk encryption and region commitments to require from the host.
5. Q5: Payroll data of a minor employee.
6. Q6: Response times for rights requests and the breach-notice wording.
7. Q7: The retention periods in §5 R5 and the privacy draft §8, before `DATA_RETENTION_ENFORCE=1`.

## 9. Sign-off

| Role | Name | Decision | Date |
|---|---|---|---|
| Counsel | | | |
| Founder (data-protection owner) | | | |
