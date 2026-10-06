# G9 navigation measurement

Recorded 2026-09-30. No menu structure was changed. D-UX-4 stays closed: grouping, search, and pack layout wait until that decision is reopened.

## What was compared

`filterNav` in `web/src/navigation/menu.ts`, locked by `menu.test.ts` (`G9 full menu versus pack sidebar`).

- **Full menu** (UX Audit Traders and Demo Traders): `NAV_PACK_DEFAULT` is absent, runtime flags for the gated modules are on. `enable_full_demo` removes `NAV_PACK_DEFAULT`.
- **Pack sidebar** (UX Pack Control): `NAV_PACK_DEFAULT` is set. These section ids are hidden:

`insights`, `manufacturing`, `payroll`, `crm`, `complaints`, `supplier-complaints`, `tickets`, `shared-tickets`, `job-cards`, `projects`, `insurance`, `contracts`.

The pack menu is a strict subset of the full menu for an owner with the same flags. That is the production default for a new company. The full menu stays on the two demo companies so this comparison can be repeated. Flag gating itself is unchanged.
