# Bizboard Privacy Policy — first draft

> **DRAFT for counsel — not legal advice. Prepared from the product's documented behaviour on
> 2026-10-24; every [bracketed] item needs a decision or confirmation.**
>
> Version key in the product: `LEGAL_PRIVACY_VERSION` (currently `draft-2026-10`,
> `backend/config/settings.py`). Every user accepts the current version at sign-in.

## Open points for counsel

1. Legal entity details and the Grievance Officer's name and contact (clauses 1, 13). Decide
   whether Bizboard needs a Data Protection Officer (only if notified as a Significant Data
   Fiduciary — unlikely at this size; confirm).
2. **Roles under the DPDP Act 2023.** This draft treats Bizboard as **Data Fiduciary** for its own
   users (owners and staff who sign in) and as **Data Processor** for the personal data inside a
   customer's business records (their customers, suppliers, employees). Confirm, including the
   edge case of an Owner who is a sole proprietor.
3. Legal basis: consent vs "legitimate uses" (section 7) for each purpose in clause 4. The draft
   relies on consent given at sign-up plus the contract; counsel to map each purpose. A consent
   notice in the form the DPDP Rules require, and whether a Consent Manager is needed.
4. **Cross-border transfer.** Hosting provider and region are not chosen; the plan is an Indian
   region (`docs/ops/HOSTED_STAGING.md`). The AI providers (OpenAI by default; DeepSeek and
   Anthropic are configurable) and Google, Cloudflare, Twilio and email providers may process
   data outside India. Confirm against any country restriction notified under section 16.
5. Third-party list in clause 6 is from the code; which ones are actually switched on at launch
   is an operations choice. Each needs [confirm].
6. Retention periods (clause 8) are proposals awaiting founder sign-off; confirm the 8-year GST
   period and the 180-day CERT-In log period are applied correctly.
7. Whether the 2011 SPDI Rules still need separate treatment for passwords and financial
   information (bank details), given the DPDP Act's commencement status at publication time.
8. Response deadline for rights requests. The product defaults to 30 days
   (`DPDP_REQUEST_DUE_DAYS`); confirm against the DPDP Rules.
9. Children: Bizboard is for businesses; confirm the age statement in clause 11 and whether any
   verifiable-consent mechanism is needed.
10. Trial-abuse hashes (clause 8.6) survive erasure. Counsel to confirm this is acceptable.
11. Local browser storage (clause 12): confirm that no cookie banner is needed for strictly
    necessary cookies and preference storage.

---

## 1. Who we are

1.1 Bizboard is run by **[Legal entity name]**, CIN **[CIN]**, registered office **[address]**
("Bizboard", "we"). This policy explains how we handle personal data when you use the Bizboard
web app, Android app and website.

1.2 Bizboard is software for Indian businesses. Two kinds of personal data pass through it:

- **Your account data** — about you as a person who signs in (Owner, staff, accountant). For this
  data we decide why and how it is used, so we are the **Data Fiduciary** under the Digital
  Personal Data Protection Act 2023 ("DPDP Act").
- **Your business's records** — the personal data of your customers, suppliers and employees that
  your business enters. Your business decides why that data is used; we process it on your
  business's behalf as its **Data Processor**, under our Data Processing Agreement. If you are a
  customer or supplier of a business that uses Bizboard, please contact that business first; we
  will pass your request to them.

## 2. What we collect about account users

| Data | Where it comes from | Notes |
|---|---|---|
| Name, email, mobile number | You, at sign-up or invite | Email verified by a code or by Google |
| Password | You | Stored only as a one-way hash |
| Google account email and name | Google, if you choose "Sign in with Google" | Only if Google has verified the email |
| Two-step sign-in secret and recovery codes | Created when you set up an authenticator app | Secret stored encrypted; codes single-use |
| One-time codes (OTP) sent by SMS or email | We create them | Stored only as a hash, expire after 10 minutes |
| Company details: business name, GSTIN, PAN, Udyam number, address | You | Used for your invoices and our GST invoice to you; PAN/Udyam may be checked with a verification service [confirm provider] |
| Your role and permissions in each company | The Owner | |
| Signed-in devices | Your browser | Device type (from the browser's user agent) and the **network prefix** of your IP address (/24 for IPv4, /48 for IPv6), never the full address; used to show your devices and warn of new sign-ins |
| Acceptance of these documents | You | Document, version, time and a hash of your IP address |
| Activity log | The app | Who did what and when (for example, created an invoice, downloaded a PDF, changed a setting) |
| Support tickets and messages | You | |
| Billing data | You and the payment gateway | Plan, subscription and payment ids, amounts, invoices, TDS certificates you upload. We never store card numbers or CVV |
| Help search text and feedback | You | Kept on our own servers |
| Telegram chat link | You, only if you link Telegram for alerts | |
| Technical logs | Your requests | See clause 7.4 |

## 3. What your business's records contain

When your business uses Bizboard it may enter: customer and supplier names, phone numbers, email
addresses, GSTINs, addresses, invoices, payments, outstanding balances and WhatsApp opt-in status;
employee names, codes and salary details for payroll; photos and files (bill photos, imported
spreadsheets, invoice PDFs). We handle these under the DPA and only on your business's
instructions.

## 4. Why we use account data

4.1 To create and run your account, sign you in securely and keep the Service working.

4.2 To bill your subscription, issue GST invoices and handle TDS claims.

4.3 To provide support, including read-only support access when the Owner grants it (clause 6.3).

4.4 To keep the Service secure: bot checks at sign-up, rate limits, sign-in alerts, fraud and
trial-abuse prevention, audit logs.

4.5 To send service emails and messages: codes, password resets, sign-in alerts, billing notices,
incident updates. [Marketing emails only with consent; every one has a one-click unsubscribe —
confirm marketing use.]

4.6 To improve the Service using aggregated, de-identified usage figures.

4.7 To meet legal duties: tax law, CERT-In directions, and lawful requests from authorities.

**Legal basis.** [Counsel: for each purpose state consent under DPDP Act section 6 or a legitimate
use under section 7. Draft position: consent at sign-up for 4.1–4.6; legal obligation for 4.7.]
You may withdraw consent at any time (clause 9); withdrawal may mean we cannot keep providing the
Service.

## 5. AI features

5.1 AI features (Insights, the Assistant, reading bill photos, and AI agents) are **off by
default**. Only the Owner can switch them on, and each change is recorded in the activity log.

5.2 When you upload a **photo of a bill**, you must first tick a box confirming you understand the
image is sent to an outside AI service. The app remembers that choice on your device until you
choose "Ask me again".

5.3 The AI service receives the image or the text needed for the request. [Counsel/founder:
confirm the provider used in production — default OpenAI; DeepSeek and Anthropic are
configurable — its region, and its data-use and retention terms (no training on customer data).]

5.4 Records of AI agent steps are kept for 180 days and then deleted.

## 6. Who we share data with

6.1 We do not sell personal data.

6.2 We share it only with service providers who help us run Bizboard, under contract, and only what
they need. Not all of these are in use at every time; the list kept current is at
[URL of sub-processor page]:

| Provider | What for | Data shared | Status |
|---|---|---|---|
| [Hosting provider, Indian region] | Servers, database, file and backup storage | All data, encrypted backups | [Not chosen yet — confirm] |
| Cloudflare | Network edge, TLS, and the bot check at sign-up (Turnstile) | IP address, browser data, request traffic | [confirm] |
| Google | "Sign in with Google" | Google sends us your verified email and name | [confirm; only if enabled] |
| Razorpay | Subscription payments | Name, email, phone, amount; you enter card/UPI details on Razorpay's page | [Not live yet — confirm] |
| Email delivery provider: [Resend / Amazon SES / Postmark] | Codes, resets, alerts, invoices | Email address, message content | [confirm which] |
| SMS provider: [MSG91 / Twilio] | One-time codes by SMS | Mobile number, code | [confirm which; off unless configured] |
| AI provider: [OpenAI / DeepSeek / Anthropic] | AI features, only when the Owner turns them on | Bill images, question text, business figures in the request | [confirm which] |
| Identity verification provider | Checking PAN and Udyam numbers | PAN / Udyam number | [confirm provider; off unless configured] |
| Telegram | Alerts, only if you link your Telegram | Your Telegram chat id, alert text | [confirm] |
| Meta (WhatsApp Cloud API) | Sending invoices to your customers who opted in | Customer phone, invoice message | [Off today — confirm before enabling] |
| Cashfree / PayU / Razorpay | Your own customers paying your invoices online | Payment details your customer enters on their page | [Sandbox only today — confirm] |
| GST Suvidha Provider / NIC | Live e-invoice | Invoice data | [Off today — confirm before enabling] |

6.3 **Bizboard support staff** can see a company's business data only when its Owner grants
access in the app: read-only, for one support request, for at most **72 hours**, optionally to
one named staff member, and revocable at any time. Every page viewed is logged and shown to the
Owner. Staff cannot act as you or change your data through this access.

6.4 Error tracking runs on our **own** servers (self-hosted GlitchTip) [in India — confirm], not
a third-party service. It is set not to collect personal data by default and scrubs IP
addresses. [If a hosted Sentry is used instead, add it to the table.]

6.5 **WhatsApp share links.** When you tap "Share on WhatsApp", the app opens WhatsApp on your
device with a message ready; you send it yourself. Bizboard does not send it.

6.6 We may disclose data if the law requires it (for example to tax authorities, CERT-In or a
court order), or to protect our users or the Service. [Counsel: business transfer clause.]

## 7. How we protect data

7.1 **Separation between businesses.** Every record belongs to one company. The database enforces
this with row-level security, and production refuses to start with it switched off; the
application also checks it on every request. Requests for another company's records get "not
found".

7.2 **Sign-in.** Passwords and one-time codes are stored only as hashes; repeated failures lock the
account for a while. Owners, Accountants and users who can post journals must use two-step
sign-in with an authenticator app in production [unless a waiver is recorded — confirm none at
launch].

7.3 **Encryption.** Data travels over HTTPS. Backups are encrypted before they leave the server
(the backup job refuses to write an unencrypted copy in production) and are kept off-host.
Two-step secrets and payment-gateway credentials are stored encrypted. Tenant exports are
encrypted. [Confirm encryption at rest on the hosting provider's disks.]

7.4 **Logs.** Our logs leave out request bodies, hash user and company ids, and mask document
numbers, passwords, tokens, codes, email addresses, mobile numbers, PAN and Aadhaar numbers.

7.5 **Audit trail.** The activity log cannot be edited or deleted through the app.

7.6 **People.** Only a small number of staff have production access; break-glass access is logged.

7.7 **Your device.** Drafts saved offline on a phone are stored unencrypted on that device. Protect
your device with a screen lock.

No system is perfectly secure. We do not hold any security certification at this time.

## 8. How long we keep data

8.1 **Account data:** while your account is active, then [period — counsel/founder to decide] after
it is closed, except where the law requires longer.

8.2 **Business records** of an active or read-only company: until the Owner asks for erasure.
After a trial or a lapsed subscription the workspace is read-only. Its data is deleted
**[90] days** after it became read-only; the Owner can choose a different period (30 days to
10 years) in Settings, and is told by email 30 and 7 days before. [Founder decision D-13,
2026-10-25; counsel to confirm. Deletion is switched on only once counsel agrees.]

8.3 **After erasure:** operational data is deleted. Statutory tax documents are kept with all
personal details removed for **8 years** (GST record-keeping), then permanently deleted. A
record that the erasure happened (company number, name, who asked, when) is kept, with no
personal data of customers or suppliers.

8.4 **Backups:** [30 daily + 12 monthly encrypted backups, plus 7 days of point-in-time recovery —
pending founder sign-off, B-8]. The backup job keeps 30 days by default today.

8.5 **Logs:** system and access logs kept for **180 days**, stored in India, as the CERT-In
Directions of 28 April 2022 require [confirm scope]. Sign-in and audit events are kept for the life
of the company. Help search events: 180 days. AI agent steps: 180 days. Error reports: 90 days.

8.6 **Trial checks:** one-way keyed hashes of a business's GSTIN, PAN, owner phone and owner email
are kept after erasure so the same business cannot start a second free trial. They cannot be
turned back into the original values. [Counsel to confirm.]

## 9. Your rights

Under the DPDP Act you can ask us to:

9.1 tell you what personal data we hold about you and who we shared it with;

9.2 correct, complete or update it;

9.3 erase it, unless the law requires us to keep it;

9.4 withdraw consent;

9.5 nominate another person to act for you if you die or cannot act; and

9.6 raise a grievance, and then complain to the Data Protection Board of India.

Owners can download their company's data at any time (Settings → export). For other requests
write to the Grievance Officer. We will check who you are (for example through your two-step
sign-in or a reply from your account email) and answer within [30 days — confirm against the
DPDP Rules]. If your data is in a business's records (you are their customer, supplier or
employee), we pass your request to that business and tell you we have done so.

## 10. Breaches

If a personal data breach happens we will tell the Data Protection Board and the people affected
as the DPDP Act and Rules require, and report to CERT-In within 6 hours where its Directions
apply. Where we are a business's processor, we tell that business so it can tell its people.

## 11. Children

Bizboard is for businesses and is not meant for anyone under 18. We do not knowingly collect
children's data. [Counsel: payroll records could include a minor employee; confirm treatment.]

## 12. Cookies and browser storage

12.1 We use only cookies needed to run the Service: a secure, HTTP-only cookie that keeps you
signed in (`bb_refresh`, sent only to our sign-in paths), a session cookie, and a security cookie
that protects forms (CSRF). [Confirm no analytics or advertising cookies at launch — none found in
the code on 2026-10-24.]

12.2 The app also stores small preferences in your browser (for example table columns, report
period, auto-print, and your AI bill-reading agreement). These stay on your device.

12.3 The bot check at sign-up (Cloudflare Turnstile) runs on Cloudflare's own terms. [confirm]

## 13. Contact and Grievance Officer

Grievance Officer: **[Name]**, **[designation]**, **[email]**, **[phone]**, **[address]**.
We will acknowledge a grievance within [timeline] and resolve it within [timeline — confirm against
the DPDP Rules and IT Rules].

## 14. Changes

We will post changes here and ask you to accept a new version at your next sign-in. For a
significant change we will also email Owners [30 days] before it applies.

Last updated: [date].
