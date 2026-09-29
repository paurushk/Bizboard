# Security Audit

**Date:** 28 September 2026  
**Scope:** Authn/authz and data exposure on the new endpoints, billing webhook acceptance, erasure, and vendor-share writes. Not a full replay of the historical GST/payment threat model.

## Controls that held

- New viewsets require `IsAuthenticated` + `HasCompany` and a module permission (`CanCreateSales` or `CanManagePolicies`). Missing feature flags raise `Http404`, not an empty 200.
- Lookups that take a foreign id (`Customer`, `Product`, `Lead`, `Ticket`, `FileAsset`, `PolicyOption`) filter `company=self.company` before use.
- `share_ticket` / `revoke_share` require an active OWNER membership on the source company. The bypass wraps only the vendor-row write. `source_ticket_id` is an integer, not a cross-tenant FK.
- `create_attachment` sniffs magic bytes (`JPEG`, `PNG`, `PDF`, `RIFF/WEBP`) and ignores the uploaded content type.
- `CompanyEraseView` is owner-only, hidden unless `ENABLE_TENANT_ERASURE` is on, and requires the company name echoed back. The export blob is built before `erase_company(..., skip_export=True)` so the hash in the response matches bytes the caller received. `skip_export` on the service is not a client switch that skips that blob.
- GST Guard override persistence goes through `gst_guard_override_membership` (owner or manager) on the invoice and credit/debit note complete paths.
- Referral evaluation rejects a reward when phone, email, GSTIN, or customer id matches the referrer, and the unique constraint collapses a double WON.

No `raw()` / string-built SQL and no `dangerouslySetInnerHTML` showed up on these paths. React text nodes escape ticket and complaint bodies.

---

### DR-011

| Field | Description |
| --- | --- |
| ID | DR-011 |
| Severity | P2 |
| Category | Security |
| Location | `backend/billing/views.py` `RazorpayWebhookView.post` lines 179–198 |
| Problem | When `RAZORPAY_WEBHOOK_SECRET` is empty, the view rejects every environment except `DJANGO_ENV=test`. The following header check is `header not in {1, true, yes} and env != "test"`. That second clause is unreachable: non-test already returned 403, and test makes `env != "test"` false. Any unsigned body is accepted in the test environment. The docstring says the test header is required. |
| Root Cause | The header gate was written as an extra `and` against the same condition the previous branch already handled. |
| User Impact | Production and staging (`DJANGO_ENV` not `test`) still refuse unsigned webhooks when the secret is unset, and refuse a bad signature when it is set. A publicly reachable host with `DJANGO_ENV=test` and no webhook secret accepts forged subscription events. That is a misconfiguration, and the dead check means the header cannot save you. |
| Reproduction | `DJANGO_ENV=test`, `RAZORPAY_WEBHOOK_SECRET=""`. `POST /api/v1/billing/razorpay/webhook/` with a subscription payload and no `X-Razorpay-Signature` and no `X-Bizboard-Test-Webhook`. The view does not return 403. |
| Recommended Fix | Require the test header whenever the secret is empty, including `DJANGO_ENV=test`. Keep the production branch that 403s when the secret is missing. Add a test that an unsigned body without the header is 403 in the test env. |
| Regression Risk | Local webhook fixtures that post without the header will start failing. They should send `X-Bizboard-Test-Webhook: 1`. |

---

### DR-012

| Field | Description |
| --- | --- |
| ID | DR-012 |
| Severity | P2 |
| Category | Security |
| Location | `backend/insurance/views.py` `PolicyViewSet.commission` lines 131–134; `backend/insurance/services.py` `open_commission` lines 134–142 |
| Problem | Commission amount is `request.data.get("amount")` with no serializer. A non-numeric value becomes an unhandled `ValidationError` / `InvalidOperation` (HTTP 500). A negative or huge decimal is stored on `CommissionReceivable.amount` (`max_digits=14`, no `MinValueValidator`). The endpoint does not check the amount against `policy.premium`. There is no idempotency key, so a double post creates two receivables. |
| Root Cause | Custom action skipped the serializer layer used by create. |
| User Impact | A desk user can book a negative commission (understating insurer receivables) or duplicate a positive one. Garbage input is a 500, which is also a noisy error path. This is same-tenant abuse or operator error, not a cross-tenant write. |
| Reproduction | `POST /api/v1/insurance/policies/{id}/commission/` as a policy manager with `{"amount": "-1"}`. Row is created. Repeat the POST. A second row appears. `{"amount": "nope"}` returns 500. |
| Recommended Fix | Decimal field, `amount > 0`, optional cap at premium, and `wrap_idempotent` with a scope that includes the policy id. Return 400 from `BusinessRuleError`. |
| Regression Risk | Clients posting string amounts that Decimal accepts (`"100.50"`) keep working. Clients posting zero need a product decision. |

## Items checked and not raised

- **Vendor snapshot contents** (`billing/ops.py` `publish_vendor_snapshot`): last login, seat counts, and churn reason are copied into the vendor company on purpose. Exposure is to the vendor owner via `VendorTenantsView`, which filters `company=cu.company`. Not an IDOR. It is a privacy design choice for the operator console.
- **Advisor book** (`AdvisorBookView`): permission is `IsAuthenticated` + `HasCompany`, then `_gate` requires `ENABLE_INSURANCE`. Non-owners are filtered to `advisor=membership` / `assigned_to=membership`. A manager does not see another advisor’s book. That is a product limit (see frontend review), not a leak.
- **Erasure hard mode** can delete a company when the flag is on and the owner confirms the name. That is the feature. Purge of tombstones after the GST retention window uses `skip_export=True` because the tombstone path was supposed to have exported already. If a tombstone was created with `skip_export` from the management command, the later purge has no archive. Operational, not an unauthenticated wipe.
