# Bizboard Terms of Service — first draft

> **DRAFT for counsel — not legal advice. Prepared from the product's documented behaviour on
> 2026-10-24; every [bracketed] item needs a decision or confirmation.**
>
> Version key in the product: `LEGAL_TOS_VERSION` (currently `draft-2026-10`,
> `backend/config/settings.py`). Every user must accept the current version at sign-in
> (`backend/accounts/legal.py`); bumping the version asks everyone to accept again.

## Open points for counsel

1. Legal entity, registered address, CIN and GSTIN of the contracting party (clause 1).
2. Plans, prices, trial, grace period and refund rules are **founder proposals** in
   `docs/roadmap/SIGNOFF_PACK_2026-10-23.md` (B-1 to B-4), not yet signed. Wording of the refund
   policy is expressly left to counsel (B-4).
3. Liability cap, exclusions and indemnities (clauses 14–15). The pilot agreement outline left
   these open too (`docs/pilot/PILOT_AGREEMENT_OUTLINE.md` §9).
4. Governing law, seat of courts or arbitration (clause 19).
5. Whether the Consumer Protection (E-Commerce) Rules 2020 apply. Bizboard sells to businesses
   only (`docs/requirements/REQUIREMENTS_BASELINE.md`: B2B traders), so likely not, but confirm,
   including for sole proprietors.
6. Whether an availability commitment is offered. A 99.5% / 30-day target exists internally
   (`docs/ops/SLO.md`) but is unsigned (sign-off pack B-6). This draft makes **no SLA or service
   credit** promise.
7. Notice periods for changes to these terms and to prices (clauses 7, 18).
8. Whether these terms, the Privacy Policy and the DPA are one click-through bundle (the product
   records acceptance of each separately; the owner also accepts the DPA per company).
9. Hindi version: the product runs in English and Hindi. Decide whether a Hindi translation is
   published and which text prevails.
10. Data retention after cancellation: founder decision D-13 (2026-10-25) is deletion [90] days after the workspace becomes read-only, the period set by the Owner (30-3650 days), with email notice 30 and 7 days before; confirm the wording and that the tax-record copy is kept 8 years
    automatically. Decide whether to add a time limit (clause 12.4).

---

## 1. Who we are

1.1 These terms are a contract between **[Legal entity name]**, a [company / LLP] incorporated in
India with CIN **[CIN]**, registered office **[address]**, GSTIN **[GSTIN]** ("Bizboard", "we",
"us"), and the business that signs up ("Customer", "you").

1.2 They cover the Bizboard web app, its Android app and its APIs (the "Service").

1.3 The Service is for businesses. By signing up you confirm you act for a business and have
authority to bind it. [Counsel: confirm whether individuals or sole proprietors need separate
treatment.]

## 2. What the Service does

2.1 Bizboard is software for billing, stock, purchases, payments, accounts and GST worksheets for
Indian businesses.

2.2 Some features are switched off, in preview or in sandbox. The in-app page **"What this does
not do"** (`/limits`) lists them. At the time of writing these include:

- GST worksheets and JSON are aids for your accountant; the Service does **not** file returns on
  the GST portal (see clause 5);
- e-invoice is preview only; live submission to the IRP is off;
- online payment collection is in sandbox until a live gateway is enabled;
- WhatsApp sending is a share link that you open and send yourself;
- drafts saved offline on a device are stored unencrypted on that device.

2.3 We may add, change or remove features. We will not remove your ability to export your data
(clause 12).

## 3. Accounts and roles

3.1 The person who creates the company account is its **Owner**. The Owner can invite users with
these roles: Owner, Manager, Sales staff, Inventory staff, Accountant, Auditor, Viewer. Only an
Owner can manage users, billing and data export.

3.2 You are responsible for everything done under your company's accounts, for choosing who gets
which role, and for removing users who leave.

3.3 Keep passwords secret. Owners, Accountants and users who can post journals must set up
two-step sign-in (an authenticator app code) where we require it.

3.4 You may sign in with a password or with Google. Google sign-in only works for an email Google
has verified.

3.5 Ownership can be transferred to another user in the app, and there is an owner recovery
process if the Owner loses access. We may ask for proof of identity and authority before
recovering an account.

3.6 One free trial per business. We use one-way hashes of the GSTIN, PAN, owner phone and owner
email to detect repeat trials (see the Privacy Policy).

## 4. Your data

4.1 Your business data (your customers, suppliers, products, invoices, payments, employees and
files) belongs to you. We claim no ownership of it.

4.2 You give us permission to store and process it only to run the Service, support you, keep it
secure, meet our legal obligations and as you instruct. The Data Processing Agreement ("DPA")
sets out how we handle personal data inside your business data. We do not sell your data.

4.3 We may use aggregated, de-identified usage figures (no party names, GSTINs, phone numbers or
amounts) to improve the Service. [Counsel: confirm; this mirrors the pilot agreement outline §6.2.]

4.4 You are responsible for having a lawful basis to put your customers', suppliers' and
employees' personal data into the Service, and for giving them any notice the law requires.

## 5. GST, tax and accounts are your responsibility

5.1 The Service calculates tax, prepares invoices and produces GST worksheets and JSON files. These
help you and your Chartered Accountant. **Bizboard does not file GST returns, does not log into
the GST portal for you and does not give tax, legal or accounting advice.**

5.2 You (and your accountant) must check figures before you file, pay tax or rely on a report.
You are responsible for correct HSN codes, tax rates, place of supply, party GSTINs and for
filing on time.

5.3 Closed periods block back-dated money changes. That is a safeguard, not a guarantee that your
books are correct.

## 6. Acceptable use

You must not:

6.1 break any law, including GST law, using the Service (for example, issuing fake invoices);

6.2 try to reach another customer's data, probe or bypass security, or test the Service for
weaknesses without our written permission;

6.3 overload the Service, use bots to sign up or get around plan limits, rate limits or bot checks;

6.4 upload malware, or content you have no right to upload;

6.5 send messages through the Service to people who have not agreed to get them (WhatsApp sending
requires the customer's opt-in on their record; see `docs/ops/WHATSAPP_CONSENT_POLICY.md`);

6.6 resell or white-label the Service without a written agreement;

6.7 copy, reverse engineer or build a competing product from the Service, except as the law allows.

We may suspend access that breaks this clause (clause 13).

## 7. Plans, trial and payment

7.1 **Plans.** [Free ₹0 · Starter ₹499 · Professional ₹1,499 · Enterprise ₹4,999 per month,
excluding GST — pending founder sign-off, sign-off pack B-1.] Each plan has limits on users,
completed bills per month, storage and API use, shown on the pricing page and in the app.

7.2 **Trial.** [14 days, no card needed, one trial per business — pending founder sign-off, B-2.]
[3 days when a live checkout takes a card at sign-up — confirm.] When the trial ends without a
paid plan, the workspace becomes **read-only**. Nothing is deleted; choosing a plan restores
editing at once.

7.3 **Payment.** Subscriptions are paid through [Razorpay — not live yet; confirm gateway], by card,
UPI Autopay or other methods the gateway offers. We never see or store your full card number or
CVV.

7.4 **GST and invoices.** Prices are exclusive of GST, charged at the applicable rate [18% —
CA to confirm]. We issue a GST tax invoice for each payment, in the app, showing your GSTIN if you
gave us one. [CA to confirm SaaS GST treatment and place of supply — sign-off pack B-1 / BB-124.]

7.5 **TDS.** If you deduct TDS on our invoice, upload the Form 16A in Settings → Billing → Claim
back TDS. We credit it to your next renewal or refund it after we verify it.

7.6 **Renewal.** Paid plans renew automatically each [month] until cancelled.

7.7 **Upgrades and downgrades.** An upgrade applies at once and we charge the prorated difference
for the rest of the period. A downgrade applies from the next renewal with no charge now. If your
use is over the lower plan's limits you may need to reduce it first.

7.8 **Failed renewal.** [For 7 days after a failed renewal you keep full use, we show a banner and
retry the payment; after that the workspace is read-only until paid — pending founder sign-off,
B-3. The product today applies 0 days.] Your data is kept.

7.9 **Price changes.** We will give at least [30 days'] notice by email and in the app before a
price change applies to you. It applies from your next renewal after the notice.

## 8. Cancellation and refunds

[Counsel to word this clause from sign-off pack B-4. Proposal:]

8.1 You can cancel at any time in the app (Billing). Cancellation takes effect at the end of the
period you have paid for. You keep full use until then; after that the workspace is read-only and
renewals stop.

8.2 [No refund for a billing period that has already started.]

8.3 [A duplicate or wrong charge is refunded to the original payment method within 7 working days
of you reporting it.]

8.4 [Annual plans, if introduced, refund unused whole months.]

## 9. Support

9.1 You can raise a support request in the app. We aim to respond within these times:
[P0 business stopped, cannot bill: 2 hours, 09:00–21:00 IST, every day · P1 money or stock looks
wrong: 4 business hours · P2 something is broken: 1 business day · P3 a question: 2 business
days — pending founder sign-off, B-10.] These are targets, not guarantees.

9.2 **Support access to your data.** Bizboard staff cannot see your business data unless the Owner
grants access in the app. A grant is tied to one support request, is **read-only**, lasts at most
**72 hours**, can be limited to one named staff member, and can be revoked at any time. Every page
staff view is logged and shown to the Owner. There is no feature that lets staff act as you.

## 10. Availability and changes

10.1 We work to keep the Service available, but it is provided without an uptime guarantee and
without service credits [unless a separate signed agreement says otherwise].

10.2 Live up/down status is at **https://[app domain]/status/**. We post incident updates there,
in the app banner and by email [and WhatsApp broadcast to pilot owners].

10.3 We may carry out planned maintenance, with notice in the app where practical.

10.4 We take nightly encrypted backups. [Recovery targets: data loss of at most 15 minutes and
service restored within 4 hours after a major failure — pending founder sign-off, B-9; internal
targets, not a promise.]

## 11. Third-party services

11.1 Some features use other providers (for example Google sign-in, the payment gateway, SMS or
email delivery, the AI service that reads bill photos). Their terms may also apply to you. The
Privacy Policy and DPA list them.

11.2 **AI features** (Insights, Assistant, reading bill photos) are **off until the Owner switches
them on**. When you upload a photo of a bill, the image is sent to an outside AI service to read
it. AI output can be wrong; you must check it before saving.

## 12. Leaving: export and deletion

12.1 **Export any time.** The Owner can download an encrypted full export and a readable export
of the company's data from the app, during and after a subscription, including while read-only.

12.2 **Erasure.** The Owner can ask us to erase the company's data [in the app, once enabled, or by
a support request]. We first take an export. Then we delete all operational data. Tax documents
the law makes us or you keep (sales and purchase invoices, credit and debit notes, returns, GST
return records) are kept with all personal details removed (names replaced, phone, email, GSTIN
and address blanked) for **8 years** and then permanently deleted.

12.3 **Backups.** Erased data can remain in encrypted backups until those backups expire [30 days
for daily backups, 12 months for monthly — pending founder sign-off, B-8]. We do not restore
erased data from backups except to recover from a disaster, in which case we erase it again.

12.4 **Inactive accounts.** [Today a read-only workspace is kept indefinitely. Counsel/founder:
decide whether to delete after a period of inactivity, with [60] days' notice.]

## 13. Suspension and termination

13.1 We may suspend or limit access, with notice where practical, if you break clause 6, fail to
pay (clause 7.8), or if needed to protect the Service, other customers or to obey the law.

13.2 We may end these terms with [30 days'] notice. If we end them without cause we will refund
any prepaid, unused whole months.

13.3 Clauses 4, 5, 12, 14, 15, 17 and 19 survive termination.

## 14. Warranties

14.1 We provide the Service with reasonable skill and care.

14.2 Apart from that, the Service is provided "as is". We do not promise it will be error-free or
that its tax calculations fit every case. [Counsel: draft disclaimers.]

## 15. Liability

15.1 Neither party limits liability for fraud, or for anything the law does not allow to be
limited.

15.2 [Bizboard's total liability under these terms is limited to the fees you paid in the
[12] months before the claim — placeholder for counsel.]

15.3 [Neither party is liable for indirect loss, loss of profit, or tax penalties and interest
arising from returns you filed — placeholder for counsel.]

15.4 [Indemnities — counsel.]

## 16. Confidentiality

Each party keeps the other's non-public information confidential and uses it only for these
terms. Your business data is confidential information.

## 17. Privacy

The Privacy Policy explains how we handle personal data of the people who use Bizboard. The DPA
explains how we handle personal data inside your business data. The Owner accepts the DPA for the
company.

## 18. Changes to these terms

18.1 We may update these terms. We will tell Owners by email and in the app at least [30 days]
before a change that reduces your rights takes effect, and ask every user to accept the new
version at their next sign-in.

18.2 If you do not agree, you can cancel and export your data before the change applies.

## 19. Law and disputes

19.1 These terms are governed by the laws of India.

19.2 [Courts at [city] have exclusive jurisdiction / disputes go to arbitration seated at [city]
under the Arbitration and Conciliation Act 1996 — counsel to decide.]

## 20. Contact and grievances

20.1 Questions: [support email]. Grievance Officer: see the Privacy Policy, clause 13.

20.2 [Notices to us: [address / email]. Notices to you: the Owner's email on the account.]
