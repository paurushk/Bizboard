# Vendor contract checklist (WP-3, BB-129): first draft, 2026-10-25

**For a first pass by the founder, then counsel's review. Not legal advice.** One row per vendor
that handles personal data at launch. Fill the cells from each vendor's own terms (their data
processing addendum, security page, sub-processor list and SLA), which need the vendor account,
so most cells are blank today. No vendor URL is guessed here.

Source lists:
- `docs/ops/SUBPROCESSORS.md`, now including the AI provider, Google, Cloudflare, Telegram,
  identity check and hosting;
- `docs/legal/drafts/PRIVACY_POLICY_DRAFT.md` §6;
- `docs/legal/drafts/DATA_PROCESSING_AGREEMENT_DRAFT.md` Annex B.

## 1. Which vendors need a contract check before launch

| Vendor | Needed at launch? | Data it gets | Status |
|---|---|---|---|
| Host (region not chosen, D-18) | **Yes** | Everything, including backups | Waiting on provider choice |
| Backup storage (separate account) | **Yes** | Encrypted backups | Waiting on provider choice |
| Email provider (Resend, Amazon SES or Postmark) | **Yes** | Email address, message text | Choose one |
| SMS provider (MSG91 or Twilio) | **Yes**, for OTP sign-in | Mobile number, code | Waiting on DLT registration |
| Razorpay (subscriptions) | **Yes**, for paid plans | Name, email, phone, amount | Skipped for now (D-03) |
| Cloudflare | If used for the edge or Turnstile | IP, traffic | Decide |
| Google ("Sign in with Google") | If enabled | Google returns email and name | Decide |
| AI provider (OpenAI by default; Anthropic or DeepSeek) | Only if AI features are offered | Bill images, question text, figures | Decide |
| Telegram | Only if alert linking is offered | Chat id, alert text | Decide |
| PAN/Udyam identity check (`IDENTITY_PROVIDER`) | Only if configured | PAN / Udyam number | Off |
| Account aggregator (`FIU_BASE_URL`) | Only if configured | Bank data the user consents to | Off |
| Meta WhatsApp Cloud, GSP/NIC, Cashfree/PayU/Razorpay collections, Tally | **No**: dark or sandbox in this release | — | Not needed at launch |
| GlitchTip | **No contract**: self-hosted, so not a sub-processor | — | Record only |

## 2. What to check, and what good looks like

| # | Check | What good looks like | Why |
|---|---|---|---|
| C1 | A data processing addendum (DPA) is offered | A standard DPA you can accept online, or sign; it names you as the customer and them as processor | DPA draft 7.3 promises customers that every sub-processor is bound |
| C2 | Data they receive | Matches §1; nothing more is sent by default | Data minimisation |
| C3 | Where data is stored and processed | India, or named countries not restricted under DPDP s.16; region selectable | DPA 11; privacy policy |
| C4 | Breach notice to you | A fixed deadline, **short enough to meet the 6-hour CERT-In report** where it applies and the 24-hour notice in DPA 9.1 (e.g. "without undue delay, within 24 h" is borderline; aim for hours) | You cannot notify faster than your vendor tells you |
| C5 | Their sub-processors | Published list, with advance notice of changes | You promise customers 30 days' notice (DPA 7.2) |
| C6 | Deletion at the end of the contract | Deleted or returned within a stated time; backups age out | DPA 10 deletion promise |
| C7 | Use of your data | Only to provide the service; **no training of AI models** on your or your customers' data | Privacy draft 5.3; DPIA R7 |
| C8 | Retention on their side | Stated, short (for example, AI request logs kept 30 days or less, or zero retention) | DPIA R5/R7 |
| C9 | Security certification | ISO 27001 or SOC 2 report available; PCI DSS for payment vendors | DPA 12 information duty |
| C10 | Uptime SLA and credits | A published SLA covering the service you use | `docs/ops/VENDOR_SLA.md` |
| C11 | Liability cap | Note the cap; check it isn't lower than what you promise customers | Terms draft |
| C12 | Termination and data export | Export in a usable format; notice period | Exit plan |
| C13 | Law and jurisdiction | Note it; Indian law and courts preferred, but large vendors rarely change this | Counsel |
| C14 | Account security | Two-step sign-in on the vendor account, named admins, keys rotatable | `docs/ops/SECRET_ROTATION.md` |

## 3. Checklist by vendor

Mark each cell ✓ (meets "good"), ✗ (does not; write the gap), or blank (not checked yet).

| Check | Host | Backup storage | Email | SMS | Razorpay | Cloudflare | Google | AI provider | Telegram |
|---|---|---|---|---|---|---|---|---|---|
| C1 DPA | | | | | | | | | |
| C2 Data | | | | | | | | | |
| C3 Location | | | | | | | | | |
| C4 Breach notice | | | | | | | | | |
| C5 Sub-processors | | | | | | | | | |
| C6 Deletion | | | | | | | | | |
| C7 Use / no training | | | | | | | | | |
| C8 Retention | | | | | | | | | |
| C9 Certification | | | | | | | | | |
| C10 SLA | | | | | | | | | |
| C11 Liability | | | | | | | | | |
| C12 Exit | | | | | | | | | |
| C13 Law | | | | | | | | | |
| C14 Account security | | | | | | | | | |

## 4. Our promises to customers, and the vendor term each depends on

| Our promise (DPA draft) | Depends on vendor term | Vendors | Risk if missing |
|---|---|---|---|
| 7.2: 30 days' notice of a new sub-processor | C5 | All | We learn of their change too late to give notice |
| 7.3: sub-processors bound by terms as protective as ours | C1, C7 | All | Breach of our DPA |
| 9.1: breach notice to the Owner within [24] hours; CERT-In within 6 hours | C4 | Host, email, SMS, AI | We miss our own deadline |
| 10: deletion after erasure (operational data deleted; anonymised tax copy kept 8 years) | C6, C8 | Host, backup, AI | Copies survive at the vendor |
| 11: data stored in India; no transfer to restricted countries | C3 | Host, backup, AI, Cloudflare | Transfer we didn't disclose |
| 12: show compliance (controls, sub-processor list, drill summaries) | C9 | Host, backup, payment | Nothing to show an auditor |

**Rule:** a promise in our DPA cannot be stricter than what the vendors behind it promise us.
Where a vendor's term is weaker (most often C4 breach notice and C3 location for AI providers),
either change vendor, change our promise, or disclose the exception in Annex B.

## 5. Sign-off

| Vendor | Terms version / date checked | Gaps | Counsel decision | Date |
|---|---|---|---|---|
| | | | | |
