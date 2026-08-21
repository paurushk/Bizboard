# UI / UX Review

## Wave 22 (2026-08-06)

GSTR export vs preview GSTIN (740); WhatsApp copy honesty (743); OCR PII disclaimer missing (744); offline.html unused (737).

## Wave 21 (2026-08-05)

Invite password required vs optional helper text (BB-000676). OWNER option dead (BB-000694).

## Wave 20 (2026-08-05)

Return/refund on prepaid invoices has no successful path (BB-000648).

## Wave 19 missed (2026-08-05)

BB-000605 unstyled MUI; BB-000612 flags invisible until reload; BB-000629 OCR confidence UX.

## Wave 19 (2026-08-05)

Missing GSTIN picker on invoice UI; Hindi gaps on ERP/POS (BB-000588); a11y on new dialogs (BB-000589); module banners vs README conflict (BB-000574).


**Date:** 2026-08-02 · **Score: 5.5 / 10**

## Strengths

- Coherent MUI shell; dashboard aging; ForbiddenPage.
- Invoice editor powerful for GST (HSN/UQC/POS gates).
- INR `en-IN` formatting.

## Issues

| Topic | Impact |
|-------|--------|
| Dense English accountant UI | Shop owners struggle |
| Phase dialogs use raw IDs | Non-tech unusable |
| No POS / counter mode | Slow vs Vyapar |
| WhatsApp labeled as share but link-only | False delivery expectation |
| Sandbox e-invoice Submit looks real | Compliance risk |
| Hindi missing | Regional MSME gap |
| Sparse aria labels | A11y fail |
| Mega invoice pages | Cognitive load |

## Recommendations

1. Feature-flag advanced modules; pilot = billing + stock + payments.
2. Party/product Autocomplete everywhere (no raw IDs).
3. Explicit “Sandbox / Preview” banners on GSTR & e-invoice.
4. POS mode roadmap.
5. Hindi catalog for primary flows.

## Score: 5.5 / 10


## Wave 8 (2026-08-03)

Mobile drawer stays open (BB-000242); menu aria-label missing (BB-000243); skip-link missing (BB-000244); RoleRoute gaps confuse VIEWER UX.

---

## Wave 9 re-audit (2026-08-03)

Independent re-verification appended `BB-000258`…`BB-000317` (60 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count: **75**. Wave 6 Open==0 invalidated.

---

## Wave 12 re-audit (2026-08-03)

Independent re-verification appended `BB-000318`…`BB-000378` (61 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count was **61**; **Open: 0** after Wave 12 open-closure (2026-08-04). Waves 10–11 Open==0 invalidated historically.

---

## Wave 13 re-audit (2026-08-04)

Independent re-verification appended `BB-000379`…`BB-000455` (77 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count: **77**. Wave 12 Open==0 invalidated. Production Readiness **3.2 / 10**.

---

## Wave 14 re-audit (2026-08-04)

Independent re-verification appended `BB-000456`…`BB-000543` (88 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count: **88**. Wave 13 Open==0 invalidated. Production Readiness **3.4 / 10**.
