# Pilot onboarding (Phase 0)

Product setup wizard design: [`docs/onboarding/NEW_USER_ONBOARDING_PLAN.md`](../onboarding/NEW_USER_ONBOARDING_PLAN.md).
When `ENABLE_SETUP_WIZARD=1`, the product path is Register → Login → `/setup`;
when off, onboarding remains checklist-only.

1. Create Owner account / use seeded pilot user (`seed_pilot_fixtures`).
2. Set Company + GST settings (state, GSTIN). **Save errors are shown — do not leave GSTIN blank if GST-registered.**
3. Import CSV (products/customers/suppliers) via Settings → Import — review preview errors before commit.
4. Record opening stock.
5. Create first purchase → Complete → verify stock.
6. Create multi-line quotation → convert → Complete invoice → wait for PDF (download may 409 while generating — retry).
7. Partial receipt + allocate.
8. Invite Staff with least privilege; verify export/cancel flags.

Pilot FAQs (freeze-accurate, not tax advice): [`FAQS.md`](FAQS.md). Training outline: [`TRAINING_A1_A26.md`](TRAINING_A1_A26.md).

## Privacy (DPDP one-liner)

BizBoard stores customer/supplier names, phones, and GSTINs for your company only. Data is used to issue invoices and reports. Contact support for export/deletion requests during the pilot. Operator posture: [`DPDP_POSTURE.md`](DPDP_POSTURE.md). See `ENV_CHECKLIST.md` for operator controls.

## Completed invoice corrections (H9-A)

Owners may amend prices/discounts/charges on completed invoices with confirmation (audited). Quantities, products, and GST rates stay locked. Do **not** use returns to fix prices. Full Credit Notes arrive in Phase 1.

## Scope honesty

Pilot is **billing + inventory + derived ledgers**.

**Feature flags** (`web/.env.example`): GSTR reports, AI insights, Tally,
e-invoice sandbox submit, and accounting UI are off unless
`VITE_ENABLE_*` or `VITE_PILOT_ADVANCED` is set. Accounting also needs
`company.accountingEnabled`.

**Do not claim:** live GST portal / NIC e-invoice filing (sandbox submit is
preview only — not filed to GSTN), WhatsApp beyond share-link, full
Manufacturing / Payroll / CRM, or multi-company.

## Scope honesty — Scope revision 2026-09-09b (KNOWN LIMITATIONS)

These are **out of the pilot**; each has a manual workaround (see
[`../FREEZE_SCOPE.md` → Scope revision 2026-09-09b](../FREEZE_SCOPE.md#scope-revision-2026-09-09b-po-call)):

| Area | Pilot workaround |
|---|---|
| Fixed assets + depreciation (D6) | Keep in existing books; post the monthly depreciation journal by hand. |
| TDS/TCS returns + certificates (D7) | Bizboard gives the TDS/TCS worksheet; the CA files GSTR-7/8 and issues Form 16A/27D from it. |
| Reverse charge / RCM (D8) | Screen out merchants with material RCM exposure, or record the RCM self-invoice + ITC manually. |
| Composition dealer + CMP-08 (D9) | Composition dealers are out of the pilot; bill of supply + the CMP-08 worksheet exist but are not gate-tested. |
| Import purchase / Bill of Entry + landed cost (D10) | Enter import purchases as a domestic purchase bill with duty / landed cost as a charge line. |
| Plan-limit enforcement (D11) | Feature-gates and count quotas are not enforced in the pilot; handle limits out of band. |

**Retained and shipping:** per-unit cess (D9b), Android app shell (D12), automated
data-erasure on request (D13 — see `DPDP_POSTURE.md`), LLM bill-extraction hardening (D14).

## Android app shell (D12) — what to expect

The BizBoard Android app in the pilot is a **shell around the web app**, not a
separate native app. Founder-ratified for the pilot on 2026-09-10 with these
limits — tell testers up front:

| Limit | What it means for the tester |
|---|---|
| **Sideloaded APK, Android only** | We send you an `.apk` file to install directly. It is not on the Play Store, and there is no iOS build in the pilot. Android will warn about installing outside the store — that is expected. |
| **No push notifications yet** | The app registers your device, but it will not send push alerts during the pilot. Check the app for updates; do not rely on notifications. |
| **Offline works for POS billing only** | You can keep taking counter sales with no signal, and they sync when you reconnect. Every other screen (purchases, reports, settings, masters) needs an internet connection. |
| **It is the web app in an app frame** | Behaviour matches the browser. Report bugs the same way. Do not expect native-only features (widgets, share targets, biometric unlock). |

You stay logged in across app restarts, and links we send you open in the app.
