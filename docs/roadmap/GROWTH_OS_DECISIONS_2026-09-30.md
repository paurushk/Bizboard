# Growth OS and features: decision log

Recorded 2026-09-30 from the founder's answers in chat. Each row states the options offered, the choice, and what it changes in [GROWTH_OS_AND_FEATURES_UNIFIED_PLAN_2026-09-30.md](GROWTH_OS_AND_FEATURES_UNIFIED_PLAN_2026-09-30.md). Where a choice reverses an earlier decision, the earlier one is named.

| # | Decision | Options offered | Chosen | Effect on the plan |
|---|---|---|---|---|
| GD-1 | Ratify the unified sequence | Ratify as written / Ratify with changes / Not yet | **Ratify with changes** (changes are GD-3 to GD-6) | Plan is accepted as the base |
| GD-2 | How to log in for the real-backend audit | Create audit company and role users / You give a login / Mock only | **Create audit company and role users** | Approval is recorded. Not yet executed. Creates "UX Audit Traders" on the dev database with owner, accountant, CA, inventory and sales users; passwords only in a gitignored local file; Demo Traders untouched. An earlier attempt to create a user was blocked by the tool, so this needs a fresh explicit go on the day |
| GD-3 | Pilot types for Phase 4 | Distributor / Services / Insurance / None yet | **All three** | Three pilots: distributor (complaints to credit note), services firm (tickets, contracts), insurance advisor (insurance pack, CRM, referrals) |
| GD-4 | Pilot order | Sequential / All three in parallel / Insurance first | **All three in parallel** | Three separate companies, three sets of grants and walks at the same time. Needs three audit companies so walks do not collide. Reverses the plan's "one company at a time" |
| GD-5 | Client events in the web app | Minimal events / Server-derived only / Not now | **Minimal events** | Allowed: first invoice, first lead, first quote, receipt from a link. No personal data. Viewed in Django admin. Phase 3 can start |
| GD-6 | Production scope | Only the 3 pilots / All companies now / Pilots first then all after a checklist | **Pilots first, then all after a checklist** | Reverses "production never gets enable-all". Production widening is allowed only after the promotion checklist passes (see below). `FREEZE_SCOPE.md` and the Freeze Gate tests must change in the same step |
| GD-7 | Phase order | Rollout in parallel with the audit / Metrics, audit, rollout / Audit before rollout | **Rollout in parallel with the audit** | Reverses "audit before rollout". Pilots see screens while they are still being audited. See the guardrails below |
| GD-8 | Timeline | 4 to 5 weeks / 10 to 12 weeks / keep 6 to 8 | **10 to 12 weeks** | Replaces "6 to 8 weeks". Reason: three parallel pilots need support time and separate audit companies |
| GD-9 | Native WhatsApp (QOS-0046) | Provide credentials / Plan only / Share link only | **Start planning; founder provides credentials and templates** | QOS-0046 moves from parked to planned. Credentials must never be committed or pasted into docs (see guardrails) |

Not asked and still open: QOS-0028 (job-work and dispatch). It stays parked until the services pilot confirms it sells AMC or warranty.

## Guardrails the choices require

These follow from GD-4, GD-6, GD-7 and GD-9. They are the conditions that keep the choices safe, not additional decisions.

1. **Rollout beside the audit (GD-7).** A pilot company gets a module only after: (a) Phase 0 passes for that module (its tests green, its flag defaults confirmed); (b) the function check for that module passes; (c) no open Critical accessibility or data-entry finding on its screens; (d) the honesty sentence for that module is on the page in English and Hindi (Holistic H5.2 to H5.6). Fixes then ship to the pilot as they land. A module that fails (b) goes to the Not-ready list and is not granted.
2. **Parallel pilots (GD-4).** One audit company per pilot type so walks and seed data do not collide. The findings ledger uses phase-prefixed IDs so three people can write without merge conflicts. Each pilot has a named contact, a start date, and a rollback (remove the per-company flag).
3. **Widening production (GD-6).** "After a checklist" means the promotion checklist: the module's Freeze Gate test is green; function check and task walk done; Critical and High findings closed; Hindi top-task pass; at least one pilot company has used it for a full cycle; one user session; a rollback is noted. Only then does `FREEZE_SCOPE.md` change, and the trial plan (`trial_plan_modules`) is edited last, because it is live for every company already on trial (Holistic decision 1). Dark modules (CRM, manufacturing, payroll) stay unnamed on the trial plan and need a plan that names them.
4. **WhatsApp (GD-9).** Credentials go into the deployment secret store and environment variables only. They are never written to the repository, this decision log, or chat. Templates must be approved by the provider before use. Build behind `ENABLE_WHATSAPP_CLOUD`; without credentials it keeps falling back to the wa.me link, and nothing is sent. Campaign sending stays out until a written consent policy exists.
5. **Audit access (GD-2).** Creating users is a write to the dev database. It is authorised in principle, but is executed only on an explicit go on the day, by a management command, with passwords in a gitignored file.

## Plan changes made

- Timeline in the unified plan is now 10 to 12 weeks, with Phase 4 running beside Phases 1 to 3.
- Phase 4 now names the three pilots and their grants.
- Section 8 of the unified plan lists these as decided.
- QOS-0046 gets a planning item (GP7 in `docs/UX_ACTION_ITEMS.md`).

## Round 2 (after the gated-module audit)

| # | Decision | Options offered | Chosen | Effect |
|---|---|---|---|---|
| GD-10 | Chart of accounts when books are turned on | Create at enable / Keep lazy and fix the screens / Leave | **Keep lazy creation, fix the screens** | GM-04 is dropped. GM-03 now owns it: books pages show one honest "no chart yet" state with a Create action, and totals that cannot be trusted show a dash |
| GD-11 | GSTR-6/7/8 stubs | Hide the menu items / One "not prepared yet" page / Keep | **Hide the 3 menu items** | Done: ids are in the not-ready list (`notReadyNav.ts`), recorded in `docs/ux/not_ready.md`, with a test. Routes still exist for direct links. GM-20 reduced to removing the H1 disclaimer |
| GD-12 | AI screens | Consent gate only / Blank keys and audit outputs / Synthetic with live keys | **Consent gate only** | GM-71 dropped. AI consent stays off everywhere while live provider keys exist in dev |
| GD-13 | First module to widen to production | Complaints / Tickets and contracts / CRM, campaigns, referrals / After pilots | **All three** | Each pilot lane runs its own promotion checklist in parallel. No order is set; each widens when its own checklist passes. Still open: which company or companies (pilot names) |

Still open: pilot company names and dates; WhatsApp sandbox or live, templates, and who holds the credentials.

## Round 3 (pilots and WhatsApp)

| # | Decision | Options offered | Chosen | Effect |
|---|---|---|---|---|
| GD-14 | How to name the pilots | Type names / Placeholders / Existing staging companies / Not yet | **Existing staging companies** | Lanes are bound to staging companies below |
| GD-15 | Distributor pilot | Pilot Inter-State / Multi-Rate / Retail GST / Shanti Traders | **Pilot Inter-State** (company 2) | Lane C1: `ENABLE_COMPLAINTS` |
| GD-16 | Services pilot | Pilot Multi-User / Non-GST Shop / Demo / new | **Pilot Multi-User** (company 5) | Lane C2: tickets, contracts, projects, workshop |
| GD-17 | Insurance pilot | New company / Demo / Multi-User / Shanti Traders | **New staging company** | Lane C3: created at go time; name still to give |
| GD-18 | Contact and rollback owner | Founder for all / one per pilot / me runs, you approve | **Founder for all three** | Recorded in the runbook |
| GD-19 | Staging changes | Prepare, approve each grant / go for all now / dev only | **Prepare commands; founder approves each grant** | `docs/ops/GROWTH_PILOT_STAGING_RUNBOOK.md` written, nothing run. Never the stack-wide overlay on staging |
| GD-20 | WhatsApp mode | Sandbox first / live / plan only | **Sandbox first** | GM-96 builds against a sandbox number and templates; live only after the pilot checklist |
| GD-21 | WhatsApp credentials | Founder in deployment secrets / a colleague / not decided | **Founder puts them in the deployment secrets** | I never see or store them. Staging `ENABLE_WHATSAPP_CLOUD` is 0 today, so a sandbox run also needs an env change on staging, which is a separate approved step |

Still open after round 3, closed in round 5: insurance company name (Pilot Insurance Advisor, GD-24), first WhatsApp template (invoice with payment link, GD-25), lane start (all three the same week, each grant still needs a go, GD-27).

## Round 4

33 build questions answered as working defaults in `GATED_MODULES_DECISIONS_ROUND4_2026-09-30.md`. Founder-only items still open: Hindi reader (Q11), user-session participants (Q30), insurance company name (Q31), lane dates and each go (Q32), WhatsApp template and credentials (Q33).

## Round 5 (answers recorded by question)

Options were offered for each; the choice is what you selected. Rows marked **differs** are where your choice differs from my proposal in round 4; the plan follows your choice.

| # | Question | Chosen | Effect |
|---|---|---|---|
| GD-22 | Commit to `ux/programme` in slices first | **No, keep working uncommitted** (differs) | No rollback point. Risk recorded below. I will not commit unless you ask |
| GD-23 | Hindi reader | **You (founder)** | Tickets are read in Hindi by you before `Done` |
| GD-24 | Insurance company name | **Pilot Insurance Advisor** | Lane C3 company name, used in the runbook |
| GD-25 | First WhatsApp template | **Invoice with payment link** | GM-95 designs this first; reminder second |
| GD-26 | User sessions | **Staff of the three pilot companies** | Sessions run during the pilots' first weeks; names come from the pilots |
| GD-27 | Lane start order | **All three the same week** (differs from staggered) | Needs three audit companies and three sets of walks at once; each grant still needs an explicit go |
| GD-28 | Campaign and contract dialog field split | **Accept** | Campaigns: Name, Type, Start date, Budget first. Contracts: Customer, Type, Start date, End date, Value first; the rest under More. Projects, job cards and referrals stay inline |
| GD-29 | Billing, gateway, contract value wording | **Accept all three** | Checkout disabled with a reason when no provider is configured; gateway says Not live when no keys are stored; contract value is a label only |
| GD-30 | First slice | **Both in parallel** (differs) | Gated screens and core invoice/purchase work run together. See the isolation rule below |
| GD-31 | Lint baseline rule | **Rewrite hook logic where needed** (differs) | Allowed, with tests. See the conditions below |
| GD-32 | Invoice primary button | **Keep all three visible** (differs) | A4-1 is closed; the completion buttons do not change |
| GD-33 | Disclosure prototype | **Wait until sessions are scheduled** (differs) | GM-99 waits; production editors unchanged meanwhile |
| GD-34 | Browser check before a UI ticket is done | **Required for every ticket that changes a screen** | As proposed |
| GD-35 | GSTR-6/7/8 heading | **Just GSTR-6 (and 7, 8)** | GM-20 heading change |
| GD-36 | Owner counts as a booker | **Yes, count the owner** (differs) | Done: `crm/onboarding.py` counts active owners and sales staff; test updated and passing |
| GD-37 | Customer 360 first slice | **All five at once** (differs) | GM-45 covers dues, tickets, contracts, referrals and opportunity value in one slice |

### Risks the differing choices create, and the conditions I will apply

1. **No commit (GD-22).** About 100 files are uncommitted, some from other sessions. A bad edit cannot be reverted cleanly. Condition: before each risky ticket I copy the touched files to a scratch folder, or you tell me to commit. Git history is not a safety net here.
2. **Both slices in parallel (GD-30).** The gated work and the invoice/purchase work can both touch `DocumentEditorShell`, `DraftLineTable` and the editors. Condition: one owner per file at a time. The gated slice does not edit those files; if it must, it waits for the other to finish.
3. **Rewrite hook logic where needed (GD-31).** POS and the editors are money screens. Condition: each rewrite needs a test that fails before and passes after, the existing POS and invoice tests stay unchanged and green, and there is no change to posting, tax, stock or permissions.
4. **All three lanes the same week (GD-27).** Condition: three audit companies, one walk script per lane, and the function check passes for each module before its grant. Each grant still needs your explicit go.
5. **All five Customer 360 sections at once (GD-37).** Larger slice; each section must still be hidden with a one-line reason when its flag is off.
6. **Owner as booker (GD-36).** It changes the CRM checklist result for owner-only companies. The pilot operator sentence must say so.
