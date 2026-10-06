# User role coverage

Taken from `CompanyUser.Role` and `capability_defaults_for_role` in `backend/accounts/models.py`, and from the permission classes in `backend/core/permissions.py`. Reconciled 2026-09-27.

`OWNER` is not a row in `capability_defaults_for_role`. Owner checks are `role == "OWNER"` inside the permission classes, except `CanManagePolicies`, which is true only when `can_manage_policies` is set. An owner does not receive that flag from the owner role.

| Role | Defaults that are true | Cannot |
|---|---|---|
| OWNER | Bypasses sales, inventory, import, purchase, payment, and journal gates by role | Manage policies unless `can_manage_policies` is granted |
| MANAGER | Inventory, import, cancel, financial reports, export, insights, assistant, sales, purchases, payments, journals | Manage policies |
| SALES_STAFF | Create sales, create payments | Inventory writes, import, cancel, financial reports, journals, policies. May look up a serial (`CanReadSerials`) and may not transition it |
| INVENTORY_STAFF | Inventory, create purchases | Sales, payments, journals, policies, import |
| ACCOUNTANT | Financial reports, export, purchases, payments, journals | Sales create, inventory, policies. Serial list is 403 |
| AUDITOR | Financial reports, export | Every write in the default set |
| VIEWER | None | Every write. Navigation hides create actions |
| POLICY_DESK | `can_manage_policies` only | Invoices, journals, trial balance, imports |

API denial is `backend/tests/tenancy/test_rbac_matrix.py`. Browser denial for sales, accountant, manager, auditor, and policy desk is `web/e2e/personas/role-boundaries.spec.ts`.

Direct URL checks in this cycle are the API denials above, plus the serial lookup denial for the accountant and the transition denial for sales staff. A penetration test was not run. Owner: security. Revisit by 2026-10-31.
