# Privacy requests and breach notices (WP-CP2)

Engineering half of the DPDP Act duties. **Counsel** confirms the time limits, the wording of every
notice, and when Bizboard acts as a data fiduciary (its own users: owners and staff) versus a
processor for its tenants (their customers' and suppliers' data) — the DPA decides the second case.
Until counsel signs, treat every request as due within 30 days and every breach as urgent.

## The register

Django admin → **Support → Data privacy requests** (`support.DataPrivacyRequest`). One row per
request, whoever it came from:

| Type | Comes from | Created by |
|---|---|---|
| `ACCESS` | A person asking for a copy of their data | Self-serve export (owner) creates the row automatically; staff log others |
| `CORRECTION` | Wrong personal data | Staff |
| `ERASURE` | Delete my data / close my company | Self-serve company erasure creates the row; staff log others |
| `GRIEVANCE` | A complaint about how data is handled | Staff |
| `CONSENT_WITHDRAWAL` | Stop using my data for X | Staff (marketing opt-out also goes through CM1's unsubscribe) |

Each row has received, due (received + `DPDP_REQUEST_DUE_DAYS`, default 30), closed, outcome, and
the staff member handling it. The admin list flags overdue rows in red.

**Steps for a request:**

1. Log it (if it wasn't created automatically). Note how you confirmed the requester is who they
   say they are (the owner's MFA sign-in, a reply from the account's email).
2. If the data belongs to a tenant's customer (Bizboard is the processor), pass it to that tenant's
   owner and record that you did; the tenant answers its customer.
3. Do the work: `ERASURE_PLAYBOOK.md` for erasure, the readable export (WP-DL1) for access.
4. Close the row with the outcome. GST law keeps tax records 8 years — an erasure keeps the
   tombstoned statutory records, and the outcome says so.

## Breach notice fields

When `INCIDENT_RESPONSE.md` says a personal data breach notice is due, fill these. **Text is for
counsel to approve before first use.**

**To the Data Protection Board:**

- Bizboard's name and contact (grievance officer, when appointed).
- When the breach happened (best estimate) and when it was noticed.
- What happened, in plain words; which systems.
- What personal data and roughly how many people and companies.
- Likely consequences for those people.
- What was done to stop it and limit harm; what is still being done.
- Whether CERT-In was told (time of that report).

**To each affected person** (through the tenant when Bizboard is their processor):

- What happened and when, in plain words.
- What data of theirs was involved.
- What they should do now (change a password, watch for fake payment requests, ignore messages
  asking for OTPs).
- What Bizboard has done.
- Who to contact.

Record every notice (who, when, channel) in the postmortem (`POSTMORTEM.md`).
