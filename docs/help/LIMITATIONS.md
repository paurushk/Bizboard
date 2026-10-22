# What Bizboard does not do (pilot and paid beta)

Shown in the app at **Help → What this pilot does not do** (`/help/pilot-limits`) and publicly
at `/limits` (link it from the pricing page and FAQ). This file is the source of truth: each
`key:` below is a line on that page, with English text in `web/src/i18n/en.ts` and Hindi in
`hi.ts` under `pilotLimits.<key>`. `guard_limitations_page` fails CI when the three drift.

Sources: [FREEZE_SCOPE.md](../FREEZE_SCOPE.md) C1–C3 and the deferred list. Turning one of these
features on for everyone (`ENABLE_TALLY`, `GSP_LIVE_ENABLED`, `ENABLE_WHATSAPP_CLOUD` defaulting
on) is already blocked by `guard_freeze_table_b_defaults` unless signed as a freeze exception;
when that happens, change or remove the matching line here in the same change.

| key | What the customer reads | Why |
|---|---|---|
| key: filing | GSTR-1 and GSTR-3B worksheets are not filing. The CA files on the portal. | C1 |
| key: einvoice | e-invoice preview is not an IRN. Live NIC generation is off. | C2 — above ₹5 Cr AATO, keep generating the IRN in your current tool and record the number |
| key: itcMatch | GSTR-2B and IMS matching of purchase bills is not done. Check input tax credit on the portal. | C1 — 2B/IMS not in this release |
| key: cost | Stock cost is a running weighted cost, not FIFO layers. | C3 |
| key: offline | Offline drafts are plaintext on the device and are wiped on sign-out. | Offline outbox design |
| key: books | Books are opt-in per company. | Books switch (shadow books post either way) |
| key: payments | Online collection is sandbox until a live gateway is configured. | Gateway go-live is per deployment |
| key: tally | Tally import (masters, opening balances, outstanding bills) is switched on by support on request. There is no live Tally sync. | `ENABLE_TALLY` granted per pilot (plan Q9) |
| key: whatsapp | WhatsApp opens a share link on your phone. Messages are not sent automatically. | `ENABLE_WHATSAPP_CLOUD` off |
| key: modules | Payroll, manufacturing, and CRM are not part of this pilot. | Dark modules |
