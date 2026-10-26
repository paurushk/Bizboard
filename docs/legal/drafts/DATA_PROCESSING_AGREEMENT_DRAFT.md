# Bizboard Data Processing Agreement — first draft

> **DRAFT for counsel — not legal advice. Prepared from the product's documented behaviour on
> 2026-10-24; every [bracketed] item needs a decision or confirmation.**
>
> Version key in the product: `LEGAL_DPA_VERSION` (currently `draft-2026-10`,
> `backend/config/settings.py`). The **Owner** of each company accepts the DPA for that company
> (`backend/accounts/legal.py`); acceptance is recorded with the version, time and a hashed IP.

## Open points for counsel

1. Roles: the Customer is the Data Fiduciary and Bizboard the Data Processor for Customer Personal
   Data (DPDP Act 2023 s.2, s.8(2)). Confirm, and confirm that a click-through acceptance by the
   Owner is a valid "contract" for s.8(2).
2. Breach notice to the Customer: the team's runbook starts clocks at **detection**, requires a
   same-day notice to affected owners for Severity 1, a CERT-In report within 6 hours, and DPDP
   notices "without delay" (`docs/ops/INCIDENT_RESPONSE.md`). This draft offers notice to the
   Customer **without undue delay and in any case within [24] hours** of becoming aware. Choose the
   number.
3. Hosting provider and region are **not chosen**; the plan is an Indian region
   (`docs/ops/HOSTED_STAGING.md`). Several sub-processors (AI providers, Google, Cloudflare,
   Twilio, email delivery) may process outside India. Draft the transfer clause (clause 11).
4. Sub-processor change notice period and objection right (clause 7).
5. Audit rights: no certification exists. Decide what evidence is offered (questionnaire, summary
   of controls, on-site audit at Customer cost) and how often (clause 12).
6. Deletion: tombstone erasure keeps anonymised statutory tax records for 8 years; hard deletion
   only after that window or on signed request. Confirm this is a Customer instruction or a legal
   obligation of the Customer that Bizboard performs for it (clause 10).
7. Liability under the DPA: same cap as the Terms, or separate? DPDP penalties are on the
   fiduciary; decide indemnities.
8. Whether the DPA also covers the Customer's own **account users** (no: draft treats Bizboard as
   fiduciary for them, see Privacy Policy).
9. Response time to assist with data-principal requests (clause 8): product default is to log
   and pass on; deadline [5 working days] is a placeholder.

---

## 1. Parties and scope

1.1 This Data Processing Agreement ("DPA") is between **[Legal entity name]**, CIN **[CIN]**,
**[address]** ("Bizboard") and the business that accepted the Bizboard Terms of Service
("Customer"). It forms part of the Terms.

1.2 It applies to personal data that the Customer, its users or its systems put into Bizboard as
part of the Customer's business records ("Customer Personal Data"), for example details of the
Customer's customers, suppliers, contacts and employees.

1.3 It does not apply to personal data about the Customer's users as account holders (name,
email, sign-in data). Bizboard handles that as Data Fiduciary under its Privacy Policy.

## 2. Roles

2.1 For Customer Personal Data, the Customer is the **Data Fiduciary** and Bizboard is the **Data
Processor**, within the meaning of the Digital Personal Data Protection Act 2023 ("DPDP Act").

2.2 The Customer is responsible for having a lawful basis for the data, for giving notices to its
data principals, and for the accuracy of what it enters.

## 3. Details of processing

| Item | Description |
|---|---|
| Subject matter | Providing the Bizboard service: billing, stock, purchases, payments, accounts, payroll, GST worksheets |
| Duration | The term of the Terms, plus the deletion and retention periods in clause 10 |
| Nature | Storage, organisation, calculation, display, export, transmission when the Customer asks (email, WhatsApp, payment links), backup, deletion |
| Data principals | The Customer's customers, suppliers, their contact persons, the Customer's employees |
| Categories of data | Names, phone numbers, email addresses, postal addresses, GSTINs, invoice and payment history, outstanding balances, WhatsApp opt-in status, employee name, code and salary details, files (bill photos, spreadsheets, PDFs) |
| Sensitive categories | Bizboard is not designed to hold health, biometric or other special data. Salary and bank-related payment data may be present. [Counsel: SPDI Rules 2011 "financial information".] |

## 4. Processing only on instructions

4.1 Bizboard processes Customer Personal Data only to provide the service, on the Customer's
documented instructions. The Terms, this DPA and the Customer's use of the product's settings are
those instructions.

4.2 Bizboard will tell the Customer if it believes an instruction breaks the law, and may refuse
to follow it.

4.3 Bizboard will not sell Customer Personal Data or use it for its own purposes, except
aggregated, de-identified usage figures that contain no party names, GSTINs, phone numbers or
amounts.

4.4 Optional features that send Customer Personal Data to third parties are **off until the
Customer turns them on**:

- AI features (Owner switch, logged in the activity log; bill-photo upload also needs the user's
  confirmation each time until remembered on that device);
- WhatsApp Cloud sending (only to customers whose record is marked opted-in; off today);
- automated payment reminders (Owner switch, default off; customers marked opted-out are skipped);
- online payment collection (sandbox today).

Turning a feature on is an instruction to process data for it.

## 5. Confidentiality and Bizboard staff

5.1 Everyone at Bizboard who can access Customer Personal Data is bound by confidentiality.

5.2 **Support access.** Bizboard support staff cannot view Customer Personal Data in the product
unless the Customer's Owner grants access in the app. A grant:

- is tied to one support ticket;
- is **read-only** (the database session itself is opened read-only, so a write fails);
- lasts at most **72 hours** and ends earlier if the Owner revokes it or the ticket is closed;
- may name a single staff member;
- requires the Owner's password and two-step check to give;
- covers only that company's data.

Every page viewed is logged (who, when, which section, search text, rows shown) and visible to the
Owner. There is no feature that lets staff sign in as a Customer user.

5.3 **Emergency access.** Production access outside a grant is limited to named engineers for
operating and repairing the service, through a time-limited break-glass session that is logged.
[Counsel: confirm wording; describe notification to the Customer, if any.]

## 6. Security measures

Bizboard maintains at least these measures (Annex A gives more detail):

6.1 Company separation enforced in the database (row-level security; production refuses to start
without it) and in the application; cross-company requests get "not found".

6.2 Role-based access within the Customer's company (Owner, Manager, Sales staff, Inventory staff,
Accountant, Auditor, Viewer); Owner-only for users, billing and export.

6.3 Two-step sign-in (authenticator app) required for Owners, Accountants and users who can post
journals, in production [unless waived — confirm none].

6.4 Passwords and one-time codes stored as hashes; sign-in rate limits and lockout; bot check at
sign-up.

6.5 HTTPS in transit; encrypted backups kept off the main server; encrypted tenant exports;
encrypted storage of two-step secrets and payment-gateway credentials.

6.6 Logs exclude request bodies and mask personal identifiers; activity log is append-only.

6.7 Card numbers and CVV are never stored; online payments use the gateway's hosted page.

6.8 Monthly restore drills from backups, and incident tabletop exercises [to be scheduled —
`docs/ops/DR_CADENCE.md` dates are blank].

Bizboard holds no security certification at this time and does not claim one.

## 7. Sub-processors

7.1 The Customer authorises Bizboard to use the sub-processors in **Annex B**.

7.2 Bizboard will give the Customer at least [30] days' notice (email to the Owner and on
[sub-processor page URL]) before adding or replacing a sub-processor. The Customer may object on
reasonable data-protection grounds; if the parties cannot agree, the Customer may end the Terms
and receive a refund of prepaid unused whole months.

7.3 Bizboard imposes data-protection terms on each sub-processor no less protective than this DPA
[confirm each vendor's terms] and remains responsible for them.

## 8. Helping the Customer with data-principal requests

8.1 If a data principal contacts Bizboard about Customer Personal Data, Bizboard records the
request, passes it to the Customer's Owner within [5 working days] and does not answer it itself
unless the Customer asks.

8.2 The product gives the Customer the tools to answer most requests itself: search and edit
customer, supplier and employee records; a full readable export; and company erasure.

8.3 Bizboard will give reasonable further help on request [at no charge / at cost — decide].

## 9. Personal data breaches

9.1 Bizboard will tell the Customer's Owner of a personal data breach affecting Customer Personal
Data **without undue delay and within [24] hours** of becoming aware of it. [Team runbook: same-day
notice to affected owners for a Severity 1 incident; clocks start at detection.]

9.2 The notice will give, as far as known: what happened and when; which systems and data; roughly
how many people and companies; likely consequences; what Bizboard has done and is doing; what
people should do (for example, ignore messages asking for codes or payments); a contact. Bizboard
will update the Customer as it learns more.

9.3 Bizboard will help the Customer meet its own duties to inform the Data Protection Board and
affected people. [Counsel: decide whether Bizboard notifies the Board directly as processor, or
only the Customer does; and who notifies data principals. The runbook assumes notices to
affected people go through the Customer.]

9.4 Bizboard reports cyber incidents to CERT-In within 6 hours where the CERT-In Directions of
28 April 2022 apply, and keeps system logs for 180 days in India for that purpose.

## 10. Return and deletion

10.1 **During the Terms.** The Owner can export all company data at any time: an encrypted full
export and a readable export. Export stays available while the workspace is read-only (after a
trial or lapsed subscription).

10.2 **On request or at the end.** On the Owner's instruction [in the app once enabled, or by
support request], Bizboard will erase the company:

- an export is taken first (its checksum recorded) unless one was just taken;
- all operational data is deleted;
- statutory tax documents (sales and purchase invoices, credit and debit notes, returns, Bill of
  Entry, GST return records) are kept with all personal details removed — names replaced with
  "[erased]", phone, email, GSTIN and address blanked — for the **8-year** GST record-keeping
  period, then deleted by an automatic daily job;
- an erasure record is kept: company number and name, who asked, when, and the export checksum —
  no personal data of customers or suppliers.

10.3 [Full deletion without the anonymised tax-record copy is available on the Customer's signed
instruction — counsel to decide whether to offer.]

10.4 Copies in encrypted backups expire with those backups [30 days daily / 12 months monthly —
pending founder sign-off]. Erased data is not restored from backup except in disaster recovery,
after which the erasure is run again.

10.5 After the Terms end, if the Customer gives no instruction, the workspace stays read-only and
is not deleted. [Decide a deletion period with notice.]

## 11. Location and transfers

11.1 Customer Personal Data is stored in **[hosting provider], [India region — not yet chosen]**,
including backups and logs.

11.2 Some sub-processors in Annex B may process data outside India. Bizboard will not transfer
Customer Personal Data to a country the Central Government restricts under s.16 of the DPDP Act.
[Counsel to complete.]

## 12. Audits and information

12.1 Bizboard will give the Customer, on request and no more than [once a year], the information
reasonably needed to show compliance with this DPA, such as a written description of its
controls, its sub-processor list, and summaries of its latest restore drill and incident
exercises.

12.2 [On-site or third-party audit: on [30] days' notice, at the Customer's cost, under
confidentiality, limited to what concerns the Customer's data — counsel to decide.]

## 13. Liability and order of precedence

13.1 [Liability under this DPA is subject to the cap in the Terms — counsel to decide.]

13.2 If this DPA and the Terms conflict on personal data, this DPA prevails.

## 14. Term and changes

This DPA lasts as long as Bizboard processes Customer Personal Data. Changes follow the Terms;
the Owner is asked to accept a new version at next sign-in.

---

## Annex A — Security measures in more detail

| Area | Measure | Source in repo |
|---|---|---|
| Tenant isolation | Every record carries a company id; Postgres row-level security; app runs as a database role that cannot bypass RLS; production/staging refuse to start with RLS off | `backend/config/settings.py` (`POSTGRES_RLS_ENABLED`), `docs/ops/RISK_REGISTER.md` R008, `tests/tenancy/` |
| Access control | Seven roles; Owner-only users/billing/export | `docs/ops/PRODUCT_BEHAVIORS_FOR_COUNSEL.md` |
| Authentication | Hashed passwords and OTPs; lockout and throttles; TOTP two-step for money roles; Google sign-in only with verified email; bot check (Cloudflare Turnstile) required in production | `backend/accounts/mfa_service.py`, `backend/accounts/google_signin.py`, `backend/config/settings.py` |
| Sessions | Refresh token in a secure HTTP-only cookie; list of signed-in devices with network prefix only; revocable | `backend/accounts/user_sessions.py`, `backend/core/netutil.py` |
| Support access | Owner-granted, read-only, max 72 h, logged per view | `backend/support/access.py`, `backend/support/models.py` |
| Encryption | Backups encrypted with GPG or age, fail closed if no key; off-host copy; encrypted tenant export | `scripts/backup.sh`, `backend/accounts/export_views.py` |
| Logging | Redaction of secrets, emails, phones, PAN, Aadhaar; no request bodies; hashed ids; 180-day retention in India planned | `backend/core/log_redaction.py`, `docs/ops/LOG_RETENTION.md` |
| Audit | Append-only activity log; PDF downloads logged | `docs/pilot/DPDP_POSTURE.md` |
| Payments | No card number or CVV stored; hosted checkout | `docs/ops/PCI_SCOPE.md` |
| Resilience | Nightly encrypted backups; monthly restore drill; RPO/RTO proposal 15 min / 4 h | `docs/ops/BACKUP_ALERT.md`, `docs/ops/DR_CADENCE.md`, sign-off pack B-8/B-9 |
| Incidents | Severity scale; CERT-In 6-hour clock; breach notice fields; postmortem within 3 business days | `docs/ops/INCIDENT_RESPONSE.md`, `docs/ops/DPDP_REQUESTS.md` |
| Erasure | Tombstone erasure with export first; coverage check in CI so no table is missed | `backend/accounts/erasure.py`, `docs/ops/ERASURE_PLAYBOOK.md` |

## Annex B — Sub-processors [all to confirm before publication]

Which of these are switched on is set per deployment. Only those switched on at launch should be
listed in the published version.

| Sub-processor | Purpose | Customer Personal Data involved | Location | Status on 2026-10-24 |
|---|---|---|---|---|
| [Hosting provider] | Compute, managed Postgres, Redis, object storage, backups | All | [India region] | Not chosen |
| Cloudflare | Edge, TLS, WAF, tunnel; [backup storage (R2) — confirm] | Traffic; [encrypted backups] | [Global] | [confirm] |
| [OpenAI / DeepSeek / Anthropic] | AI features, only if Owner enables | Bill images, business figures in a request | [Outside India — confirm] | Configurable; default OpenAI |
| [Resend / Amazon SES / Postmark] | Sending emails the Customer triggers (invoices, reminders) | Recipient email, message content | [confirm] | [confirm which] |
| [MSG91 / Twilio] | SMS | Phone number, message | [confirm] | Off unless configured |
| Meta Platforms (WhatsApp Cloud API) | Invoice messages to opted-in customers | Customer phone, invoice message | [Outside India] | Off |
| Razorpay / Cashfree / PayU | Online collection from the Customer's customers | Payer details entered on gateway page, amount | India | Sandbox only |
| GST Suvidha Provider / NIC | Live e-invoice submission | Invoice data incl. buyer GSTIN and address | India | Off |
| Telegram | Alerts to users who link Telegram | Alert text (may name a customer or item) | [Outside India] | [confirm] |

**Not sub-processors:** error tracking is self-hosted (GlitchTip) on Bizboard's own servers
[confirm India region]; Help analytics stay on Bizboard servers; WhatsApp share links (`wa.me`)
are sent by the user from their own device.
