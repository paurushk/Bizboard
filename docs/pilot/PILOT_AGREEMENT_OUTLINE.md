# Pilot Participation Agreement — Working Draft

> **Status:** SR-57 working draft for **legal review**. Not executed copy. The
> Operator's counsel must review §§9–11 (liability, indemnity, governing law),
> confirm the DPDP data-processing language, and produce the signature form.
> Bracketed `[…]` items are decisions for the Operator.

**Parties.** This Pilot Participation Agreement ("Agreement") is between
`[Operator legal entity]` ("Operator") and the business identified in the
signature block ("Pilot Firm"), a single legal entity operating under one GST
registration.

**Purpose.** The Pilot Firm will evaluate the Operator's "Bizboard" software (the
"Service") for its day-to-day B2B trade billing, inventory and ledgers during a
time-boxed pilot.

---

## 1. Term

1.1 The pilot runs for **4 weeks** from the date onboarding is completed
("Onboarding Date"), unless extended by written agreement or ended earlier under
§7.

1.2 There is **no automatic renewal** and no obligation on either party to
continue to a paid subscription.

## 2. Fees

2.1 The Service is provided **free of charge** for the Term. The Operator may
introduce paid plans afterwards; any such plan is a separate agreement.

## 3. Access and accounts

3.1 The Operator provisions access for the Pilot Firm's owner and up to the
Pilot Firm's staff seats.

3.2 The Pilot Firm is responsible for its users' credentials and for use of the
Service under its account.

## 4. What the Pilot Firm will do

4.1 Use the Service as its primary system for the trade loop (purchase bill →
stock/AP → quotation → order → delivery challan → invoice → receipt →
allocation → statement) for the Term.

4.2 Provide accurate master data and opening balances.

4.3 Take part in weekly feedback calls and complete one month-end close with its
own Chartered Accountant.

## 5. What the Operator will do

5.1 Provide onboarding support, weekly check-ins, and fixes for
pilot-blocking defects during the Term, on commercially reasonable efforts
(see `SUPPORT_SLA.md`).

5.2 Make available the frozen pilot feature set: billing, inventory, derived
ledgers, receipts and allocation, and month-end GSTR-1 / GSTR-3B and trial
balance **worksheets**.

## 6. Data

6.1 **Ownership.** All data the Pilot Firm enters remains the Pilot Firm's
property. The Operator claims no ownership of it.

6.2 **Use.** The Operator processes that data only to operate the Service for the
Pilot Firm and to provide support. The Operator will not sell it or use it to
build a profile of the Pilot Firm for unrelated purposes. Aggregated, de-
identified usage metrics (no party names, GSTINs, phone numbers or amounts) may
be used to improve the Service.

6.3 **Sub-processors.** The Operator uses the sub-processors listed in
`DPDP_POSTURE.md` (e.g. payment gateway sandbox, SMS provider, model provider for
bill extraction). The list may change on notice.

6.4 **Isolation.** The Pilot Firm's data is company-scoped and is not visible to
other pilot firms.

6.5 **Export.** The Pilot Firm may request a full export of its company data at
any time and at the end of the Term, in a documented format.

6.6 **Erasure.** On the Pilot Firm's written request the Operator will erase the
Pilot Firm's data. Erasure runs an export first, then removes all operational
data; statutory tax documents are retained in **anonymised** form (party names,
contact details and GSTINs removed) for the **8-year GST retention period** and
then permanently purged. An immutable log of the erasure (company id, date,
requester — no party PII) is kept. See `DPDP_POSTURE.md`.

6.7 **Security.** The Operator applies commercially reasonable technical and
organisational measures. This Agreement is not a warranty of a specific security
certification.

## 7. Exit

7.1 Either party may end the pilot at any time on written notice.

7.2 On exit the Operator provides the data export under §6.5, and, on request,
erases the data under §6.6.

## 8. Statutory disclaimer (Pilot Firm acknowledges)

8.1 GSTR-1, GSTR-3B and CMP-08 outputs are **calculation worksheets** for the
Pilot Firm and its CA to file on the GST portal. They are **not** live GSP portal
filing.

8.2 e-invoice / e-way outputs, where shown, are **preview / manual-record only**.
The Service does not generate live IRNs or e-way bills during the pilot; a Pilot
Firm above the applicable turnover threshold continues to generate them in its
existing utility.

8.3 Online payment collection, if enabled, runs in **sandbox** — no live
settlement.

8.4 The Pilot Firm remains solely responsible for its own statutory compliance,
returns and filings.

## 9. Warranties and liability — **legal to finalise**

9.1 The Service is provided **"as is"** for the Term, with no warranty of
uptime, error-free operation or fitness for a particular purpose.

9.2 `[Liability cap — e.g. the Operator's aggregate liability is limited to
₹[amount] / to direct damages only / excluded to the extent permitted by law.]`

9.3 `[Exclusion of indirect, incidental and consequential damages.]`

## 10. Confidentiality

10.1 Each party keeps the other's non-public information (including the Service's
non-public features and the Pilot Firm's business data) confidential and uses it
only for the pilot. `[Standard mutual NDA wording — legal.]`

## 11. General — **legal to finalise**

11.1 `[Governing law and jurisdiction.]`
11.2 `[Assignment, notices, entire agreement, amendment in writing, severability.]`
11.3 `[Whether a separate DPA / processor addendum is attached.]`

---

## Signature block

| | Operator | Pilot Firm |
|---|---|---|
| Legal name | `[Operator entity]` | |
| GSTIN | | |
| Signatory name | | |
| Title | | |
| Signature | | |
| Date | | |

## Open items for the Operator / legal

- Operator legal entity name + registration details (§ Parties, 9).
- Liability cap and indemnity wording (§9).
- Governing law / jurisdiction (§11).
- Confirm the §6 DPDP language against counsel's data-processing template; decide
  whether a standalone DPA is attached.
- Confirm the 8-year retention figure in §6.6 with the CA / counsel.
- Support SLA numbers referenced from `SUPPORT_SLA.md`.
