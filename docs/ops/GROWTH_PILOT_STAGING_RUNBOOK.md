# Growth pilots on staging: per-company grant runbook

**Status: prepared, not run.** Decided 2026-09-30 (`docs/roadmap/GROWTH_OS_DECISIONS_2026-09-30.md`, GD-14 to GD-27): the founder approves each grant before it runs. All three lanes start the same week. Nothing here is applied until the founder says "go" for that lane.

**Never** use `docker-compose.fulldemo.yml` or `BB_FULL_DEMO=1` on staging. It is stack-wide and would change every staging company. Everything below is per company.

## Lanes

| Lane | Pilot type | Staging company | Owner login | Grants | Contact and rollback owner |
|---|---|---|---|---|---|
| C1 | Distributor (complaints to credit note) | **Pilot Inter-State** (company 2) | `pilot-c2@bizboard.local` | `ENABLE_COMPLAINTS` | Founder |
| C2 | Services firm (tickets, contracts, projects, job cards) | **Pilot Multi-User** (company 5) | `pilot-c5@bizboard.local` | `ENABLE_SUPPORT_TICKETS`, `ENABLE_CONTRACTS`, `ENABLE_PROJECTS`, `ENABLE_WORKSHOP` | Founder |
| C3 | Insurance advisor (insurance pack, CRM, campaigns, referrals) | **Pilot Insurance Advisor** (new staging company, to be created) | new owner and a policy-desk user | `pack_grant: insurance`, `ENABLE_INSURANCE`, `ENABLE_REFERRALS` | Founder |

Shanti Traders (company 7) and Demo (company 6) are not part of any lane. Shanti Traders looks like a real user; do not touch it.

## Preconditions for every lane (from the decision log guardrails)

1. Phase 0 passes for the module: its backend tests green (`test_growth_os.py` and the related complaint, contract, referral tests passed on 2026-09-30).
2. The module's function check passes on staging (open, list, create one record, reach the main action).
3. No open Critical accessibility or data-entry finding on its screens.
4. Its honesty sentence is on the page in English and Hindi.
5. The founder has said "go" for this lane.

**Staging image warning.** `bizboard-api:latest` was rebuilt on the dev stack on 2026-09-30 and now contains newer migrations than the staging database. Do not recreate the staging api, worker or beat containers until staging has run `migrate` (`.\scripts\compose-env.ps1 staging --profile migrate run --rm migrate`). Running containers keep their old image until recreated, so the grants below work on the current staging code. Screen fixes from the audit reach staging only after a planned rebuild, migrate and recreate.

## C1: distributor, Pilot Inter-State

Grant (company JSON only; the shared trial plan is not touched):

```powershell
.\scripts\compose-env.ps1 staging exec api python manage.py grant_company_flag --email pilot-c2@bizboard.local --flag ENABLE_COMPLAINTS --on
```

Check: sign in as that owner, open `GET /api/v1/feature-flags/`, expect `ENABLE_COMPLAINTS: true`, and expect `ENABLE_COMPLAINTS` unchanged for companies 1, 3, 4, 5. Customer 360 and the portal stay as the trial grants them.

Walk: complaint, inspect, approve, return, credit note (GM-55).

Rollback:

```powershell
.\scripts\compose-env.ps1 staging exec api python manage.py grant_company_flag --email pilot-c2@bizboard.local --flag ENABLE_COMPLAINTS --off
```

## C2: services firm, Pilot Multi-User

```powershell
$o = "pilot-c5@bizboard.local"
foreach ($f in "ENABLE_SUPPORT_TICKETS","ENABLE_CONTRACTS","ENABLE_PROJECTS","ENABLE_WORKSHOP") {
  .\scripts\compose-env.ps1 staging exec api python manage.py grant_company_flag --email $o --flag $f --on
}
```

Check: the four flags true for company 5 only. The contract value label must read "Value is for the renewal list. It does not create an invoice." before the grant is announced. There is no link to a recurring invoice. CRM is **not** part of this lane; add it only if the pilot asks, through its plan (Holistic H5.1). If CRM is added, the checklist counts the owner as a booker (GD-36).

Rollback: the same loop with `--off`.

## C3: insurance advisor, Pilot Insurance Advisor

1. Create the company through normal signup on staging (owner account). The company name is **Pilot Insurance Advisor**.
2. Add a policy-desk user (role `POLICY_DESK`, capability `can_manage_policies`) through the app's Users screen.
3. Grant the insurance pack. CRM is a dark module: a bare `ENABLE_CRM: true` stays off for a subscribed company. The sanctioned path is `pack_grant: "insurance"`, which turns CRM on together with campaigns and referrals (`docs/ops/DARK_MODULE_GRANT.md`, `core/services/feature_flags.py`). One reviewed Django shell edit, not a new command:

```powershell
.\scripts\compose-env.ps1 staging exec api python manage.py shell -c "from accounts.models import Company; c=Company.objects.get(name='Pilot Insurance Advisor'); f=dict(c.feature_flags or {}); f.update({'pack_grant':'insurance','ENABLE_INSURANCE':True,'ENABLE_REFERRALS':True}); c.feature_flags=f; c.save(update_fields=['feature_flags','updated_at'])"
```

Check: `ENABLE_CRM`, `ENABLE_INSURANCE`, `ENABLE_REFERRALS` true for that company only. Insurance screens need the policy-desk user (owners see the "not on yet" page by design). The CRM checklist counts an active owner as a booker (GD-36); tell the operator that an owner-only company shows that step done.

Walk: lead, option set, policy, renewal diary (GM-46 plus the renewal walk).

Rollback: remove `pack_grant`, `ENABLE_INSURANCE`, `ENABLE_REFERRALS` from the company flags with the same shell pattern.

## Record of runs

| Date | Lane | Company | Action | By | Result |
|---|---|---|---|---|---|
| | | | none yet | | |

## After a grant

Baseline the lane's metrics first (GM-92), then let fixes ship as they land (GD-7). A module that fails its function check goes to `docs/ux/not_ready.md` and is not granted.
