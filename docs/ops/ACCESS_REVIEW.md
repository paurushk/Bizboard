# Access review / offboarding (4.7)

Quarterly. Named humans own the rows. Same-day offboard when employment ends.

| Check | How | Owner | Last date |
|---|---|---|---|
| Active Owners | Settings → Users; at least two if possible | Founder | |
| Staff vs role | Invite role matches job; Viewer has no writes | Owner | |
| Billing override | `billing_override_active` only for support tickets | Ops | |
| Django staff/superuser | `is_staff` allowlist | Eng | |
| Staging vs prod secrets | Rotation drill `secret_rotation_drill` | Ops | |
| Ex-employee | Deactivate membership the same day; revoke sessions | Owner | |

Do not leave a personal email as the only Owner. Transfer ownership before offboard.
