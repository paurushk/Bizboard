# Bizboard Stabilization Plan — maximum quality, minimum tokens

*Written 2026-10-23. Owner: founder. Status lives in `qos/backlog/*.yaml`, not here.*

## Where we actually are (2026-10-23)

- Almost everything is committed. 29 files are uncommitted (mostly GlitchTip, load and ops docs) and the branch is 2 commits ahead of its remote.
- CI already runs a strong set of gates: invariant sweep, mutation audit, Postgres RLS, determinism probe, migration-ledger gate, nightly ledger, backup-restore drill, ZAP and CodeQL. **The machinery exists. What's missing is proof that it passes, and closing the loop.**
- The Q-OS backlog has 155 items. **68 are `fixed` but only 25 are `verified`.** That gap is the single biggest quality lever.
- About 30 open items belong to the founder: CA sign-off, Hindi review, device checks, decisions. LLMs cannot close these.
- Property-based tests (Hypothesis) appear in only 2 test files, and money is the core of the product.

## Status (2026-10-25)

| WP | State | Evidence / what is left |
|---|---|---|
| WP-1 Land and baseline | Done locally; **not committed** | Commit/push needs the founder's approval; GitHub CI status unseen (`gh` not logged in) |
| WP-2 Verify the fixed items | Done | `qos/tools/verify_fixed.py`: every `fixed` card now `verified` (54 on Postgres, 17 by direct check, browser or mutation run; `qos/evidence/verify_fixed_2026-10-2*.md`) |
| WP-3 CI gates on Postgres | Done locally | Full strict sweep on Postgres 17 (16 chunks): 14 findings, all fixed: 3 product bugs (workshop line / gateway refund / stock count `FOR UPDATE` on a nullable join; agents report money format), 8 tests that build broken journals (`broken_ledger_ok` marker), 3 test issues. Real-broker lane and mutation lane were silent no-ops (`\|\| true`); both fixed. Branch protection still to set (founder) |
| WP-4 Money invariants as properties | Done | Ledger state machine adds TDS receipts, voids, sales returns, purchase credit notes, IGST sales, godown transfers; `gst` invariants checked; 100 examples green |
| WP-5 Mutation score | Done | First real run (the CI lane had never run): place_of_supply 98.5%, accounting 62.8%, inventory 44.4%, tds_worksheets 39.9%. After new TCS/TDS-worksheet and valuation tests and a wider selection: **99.2% / 82.0% / 90.2% / 95.8%**, all above 80%; ratcheted in `scripts/ci_gates/mutation_baseline.json` |
| WP-6 Lead-pilot journeys | Done | 17 journeys mapped (`qos/journeys.yaml` `golden:`); new `lead-pilot-gaps.spec.ts` (day close, no printer, credit block, month end, TCS, dunning, bank match); all green at desktop and phone on live Django + Postgres; nightly workflow `lead-pilot-journeys.yml` |

Bugs found and fixed on the way: QOS-0154 (phone void sheet not a dialog), QOS-0155 (Hindi button off-screen on phones),
QOS-0156 (reload during a token refresh signed the user out), the workshop/refund/stock-count Postgres crashes above.

## The principle

> **Quality = claims backed by evidence.** Spend LLM tokens only where judgment is needed.
> Let scripts and CI do everything deterministic, for free.

| Use scripts / CI (0 tokens) | Use a cheap model (Haiku / Sonnet) | Use the strong model (Opus) |
|---|---|---|
| running tests, Postgres lanes, e2e, mutation, flipping `fixed→verified` | writing a missing test from a backlog card, Hindi string checks, sorting failures into groups | money and tax logic review, concurrency, tenant isolation, root-causing a failure |

## Token rules for every session that runs this plan

1. **One work package (WP) per fresh session.** Paste only the WP card below; don't pass on chat history.
2. **Read via grep, never whole files.** This applies especially to the generated files listed in `CLAUDE.md`.
3. **Start from the failing output**, not from exploring: run the command first, then read only the code the stack trace names.
4. **Fan-out searches go to an `Explore` subagent.** Only its conclusion comes back.
5. **Re-runs are scripts.** If an LLM runs the same command twice, turn it into a `qos/tools/` script.
6. **The session ends by updating the YAML card** (`lifecycle`, evidence). It never writes a new prose report.
7. **Reviews use a fresh session.** The session that wrote the code never signs it off.

## Work packages, in order of impact per token

Each card shows its token cost and its impact.

### WP-1 · Land and baseline *(tokens: tiny · impact: high)*
- Commit the 29 files and push. Run the full CI on the branch, then merge to `main`.
- Record which CI jobs are green and which are red or skipped in `qos/evidence/baseline-2026-10.md`.
- **Done when:** `main` contains everything, with a list of red jobs and one QOS card per red job.

### WP-2 · Verify the fixed items *(tokens: low · impact: very high)*
- Write a script, `qos/tools/verify_fixed.py`. For each `lifecycle: fixed` card with a `test_required`, run that test on **Postgres**. If it passes, set `verified`, recording the commit SHA and date. If it fails, reopen the card.
- Cards with no `test_required`: a Sonnet session writes one test per card. It reads only the card and the files the card names.
- **Done when:** `fixed` = 0. Every item is either `verified` or reopened.

### WP-3 · All CI gates green on Postgres *(tokens: medium · impact: very high)*
- Make every red job from WP-1 green, or open a card for it with a date. Concurrency and RLS tests only count on Postgres.
- Make the invariant sweep, the nightly ledger and the backup-restore drill **required** checks.
- **Done when:** branch protection requires those jobs, and they have been green for 7 days in a row.

### WP-4 · Money invariants as properties *(tokens: medium · impact: very high)*
- Use Hypothesis state-machine tests. They run random sequences of the following operations against one tenant:
  - sale, return, credit note, debit note;
  - purchase;
  - payment with TDS;
  - stock transfer, manufacturing issue and receipt.
- After every step, check these invariants:
  - debits equal credits;
  - stock equals the sum of stock movements, never negative unless allowed;
  - each invoice's GST equals the sum of its lines;
  - party outstanding equals invoiced minus received minus TDS minus notes;
  - no data crosses between tenants.
- One Opus session designs the state machine; after that, CI runs it every night with more examples.
- **Done when:** it runs nightly with ≥ 500 examples, and every counter-example it finds becomes a QOS card plus a regression test.

### WP-5 · Mutation score on the money modules *(tokens: low · impact: high)*
- Point the existing `mutation-audit` job at sales, purchase, ledger, GST/TDS and inventory valuation. Record a baseline mutation score per module.
- For surviving mutants, Sonnet adds the missing assertion. It sees only the mutant diff and the nearest test.
- **Done when:** each money module scores at least 80% and CI blocks any drop.

### WP-6 · Lead-pilot journeys end to end *(tokens: low · impact: high)*
- Only the lead pilots: the semi-wholesaler (ARCH-03) and the counter retailer (ARCH-01). Run their cells in `qos/journeys.yaml` as Playwright specs on staging every night, at desktop size and at Android-phone size.
- The LLM only sorts failures: it reads the trace and screenshot and files a card. It doesn't re-run anything.
- **Done when:** every ARCH-03 and ARCH-01 cell has a spec and the run has been green for 7 nights in a row.

### WP-7 · Production signal loop *(tokens: low, recurring · impact: high after launch)*
- A daily scheduled routine pulls new GlitchTip issues, slow endpoints and support tickets. It groups them by root cause and creates or updates QOS cards. It never auto-fixes.
- Error budget: if errors per active tenant per day go above the threshold, new feature work pauses.
- **Done when:** the routine has run for 7 days and every error group has a card.

### WP-8 · Usability, once, done properly *(tokens: medium, one-off · impact: high)*
- For the top 10 journeys, an Opus session walks the running app in the browser as two personas, P2 (counter clerk) and P5 (resident bookkeeper), in Hindi and on a phone-size screen.
- It scores each journey on clicks to finish, recovery after an error, jargon and empty states, and files cards. It does not redesign anything.
- Then **5 real users** do the same journeys while being watched. Their findings outrank the LLM's.
- **Done when:** P1 usability cards are fixed and re-walked.

### WP-9 · Founder pack, batched *(tokens: ~0 · impact: unblocks release)*
- Put every `owner: founder` open card into three sittings:
  - **CA day:** go through `docs/ca/CA_SIGN_OFF_CHECKLIST.md` in one session.
  - **Hindi:** merge every `*_HINDI_REVIEW.csv` into one sheet for one reviewer.
  - **Device and decisions:** one afternoon on low-end Android, plus the pending yes/no decisions.
- An LLM only prepares the packs and records the answers back into the cards.
- **Done when:** no `open` founder cards remain, other than ones explicitly deferred.

### WP-10 · Keep it stable *(ongoing)*
- **Feature freeze** until WP-1 to WP-6 are done. New work needs a QOS card.
- Changes to money or stock code need a fresh-session review (`/code-review high`) and a passing property test.
- **Rollout:** flags default off; turn on one pilot at a time and watch WP-7 signals for 7 days before widening.

## Order and rough effort

```
Week 1: WP-1, WP-2, WP-3 (start)        — make the existing proof real
Week 2: WP-3 (finish), WP-4, WP-5       — make money provably right
Week 3: WP-6, WP-7, WP-8 (LLM walk)     — make journeys and production observable
Week 4: WP-8 (real users), WP-9         — human sign-offs; then pilot rollout under WP-10
```

## The exit test: "utmost quality" means all of these are true

- [ ] 0 `fixed`-but-unverified cards; 0 open P0 or P1 cards
- [ ] Required CI (including Postgres, invariant sweep, nightly ledger, restore drill) green 7 days running
- [ ] Money property tests nightly; mutation score ≥ 80% on money modules
- [ ] ARCH-03 and ARCH-01 journeys green nightly on staging, at desktop and phone size
- [ ] CA, Hindi and device sign-offs recorded in the cards
- [ ] 5 real-user sessions done; their P1 findings fixed
- [ ] Error-budget routine live on GlitchTip
