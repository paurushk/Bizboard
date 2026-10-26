# Data retention for read-only workspaces (D-13, 2026-10-25)

**Rule.** When a workspace has no paid or trial access it becomes read-only (the owner can still
sign in, view and export). Its data is deleted a set number of days later: **90 by default**; the
owner can choose 30 to 3,650 days on **Settings > Backup / Export > Data retention**. The period
cannot be changed while the workspace is read-only; renewing the plan stops the clock.

**What deletion means.** `accounts.erasure.erase_company(mode="tombstone")`: operational data is
deleted; statutory tax documents stay with party details removed for the 8-year GST window, then
`purge_expired_tombstones` removes them. An encrypted export digest is recorded first.

**Daily job.** `accounts.tasks.apply_data_retention_task` (beat `accounts-data-retention-daily`,
04:40 IST) for every live company:

| State | What happens |
| --- | --- |
| Has paid or trial access | `Company.read_only_since` is cleared |
| Just became read-only | `read_only_since` is set to now |
| 30 days or less before the deletion date | Owners get an email and an in-app notice, once |
| 7 days or less before | A second email and in-app notice, once |
| On or after the deletion date | Erased **only if `DATA_RETENTION_ENFORCE=1`**; otherwise logged as "would erase" |

Sandbox copies and companies with `billing_override_active` are never read-only, so never deleted
by this job.

**Switching it on.** Set `DATA_RETENTION_ENFORCE=1` in the env file only after counsel confirms the
policy wording (terms and privacy policy drafts in `docs/legal/drafts/`). Before that, check the
log lines `retention: ... would erase` to see which companies would go.

Code: `backend/accounts/retention.py`; tests: `backend/tests/test_data_retention.py`.
