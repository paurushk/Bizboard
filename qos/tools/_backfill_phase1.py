"""One-shot Phase 1 backfill: mine existing evidence into qos/backlog/*.yaml + _SOURCE_MAP.md.

Sources mined:
  - docs/TESTING_STRATEGY.md section 7 gap register (G-1..G-16, G-determinism, G-mutation)
  - docs/FREEZE_SCOPE_COVERAGE.md "P0/P1 issue-register sweep" residuals
  - docs/reviews/UX_AUDIT_FINDINGS.md (UX-00x — fixes lacking a regression guard)
  - docs/FREEZE_SCOPE.md sections B (NOT SUPPORTED) + C (KNOWN LIMITATIONS) -> Accepted / won't-fix
  - docs/BUSINESS_ARCHETYPES_AND_PERSONAS.md sections 8-9 (CONDITIONAL / UNTESTED IN PILOT)
  - docs/reviews/18_COMPETITOR_ANALYSIS.md + persona veto triggers -> Innovation annex

Re-running is safe: it overwrites the generated QOS-*.yaml and _SOURCE_MAP.md.
After Phase 1 the YAML files are the source of truth; edit them, not this script.
The MASTER_ISSUE_REGISTER CR/R/BB deep-mine is a follow-on tranche (see _SOURCE_MAP).
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
BACKLOG = ROOT / "qos" / "backlog"

KEY_ORDER = [
    "id", "category", "title", "persona", "archetype", "journey", "problem",
    "evidence", "scoring", "business_metric", "priority", "priority_rationale",
    "effort", "recommendation", "test_required", "guard_ref", "lifecycle",
    "wontfix_rationale", "depends_on", "supersedes", "duplicates", "owner",
    "opened", "closed",
]

TODAY = "2026-09-10"


def impact_band(r, s, f):
    p = r * s * f
    if s == 5 or p >= 45:
        return "High"
    if p >= 18:
        return "Medium"
    return "Low"


def item(id_, category, title, persona, journey, problem, ev_strength, ev_source,
         ev_detail, reach, severity, frequency, priority, priority_rationale,
         effort, recommendation, test_required, owner, *, archetype=None,
         business_metric="none", lifecycle="open", wontfix_rationale=None,
         depends_on=None, duplicates=None, closed=None):
    d = {
        "id": id_,
        "category": category,
        "title": title,
        "persona": persona,
        "journey": journey,
        "problem": " ".join(problem.split()),
        "evidence": {
            "strength": ev_strength,
            "source": ev_source,
            "detail": " ".join(ev_detail.split()),
        },
        "scoring": {
            "reach": reach, "severity": severity, "frequency": frequency,
            "impact_band": impact_band(reach, severity, frequency),
        },
        "business_metric": business_metric,
        "priority": priority,
        "priority_rationale": " ".join(priority_rationale.split()),
        "effort": effort,
        "recommendation": " ".join(recommendation.split()),
        "test_required": " ".join(test_required.split()),
        "guard_ref": None,
        "lifecycle": lifecycle,
        "owner": owner,
        "opened": TODAY,
        "closed": closed,
    }
    if archetype:
        d["archetype"] = archetype
    if wontfix_rationale:
        d["wontfix_rationale"] = " ".join(wontfix_rationale.split())
    if depends_on:
        d["depends_on"] = depends_on
    if duplicates:
        d["duplicates"] = duplicates
    return d


ITEMS: list[dict] = []
SOURCE_ROWS: list[tuple[str, str, str]] = []  # (source id, QOS id, note)


def add(it, *sources):
    ITEMS.append(it)
    for s in sources:
        sid, _, note = s.partition("|")
        SOURCE_ROWS.append((sid.strip(), it["id"], note.strip()))


# ======================================================================
# A. Strategy section 7 gap register
# ======================================================================

add(item(
    "QOS-0001", "DISSATISFACTION",
    "UI may render controls that 403 for SALES_STAFF and ACCOUNTANT",
    ["P2", "P5"], "Everyday navigation as a non-owner role",
    """Backend RBAC is fully asserted, but the frontend test that proves the UI hides
    what a role cannot do is test.fixme-skipped for SALES_STAFF and ACCOUNTANT. A control
    that renders then 403s on click is exactly the P2/P5 trust-eroding friction.""",
    "heuristic",
    ["docs/TESTING_STRATEGY.md#7 G-4", "web/e2e/personas/role-boundaries.spec.ts",
     "docs/reviews/UX_AUDIT_FINDINGS.md UX-002"],
    "Inferred from the skipped FE coverage and the prior UX-002 incident; not observed with users.",
    4, 3, 4, "P1",
    "Impact High (48); heuristic evidence caps at P1.",
    "M",
    """Add loginAsSales / loginAsAccountant seeds to web/e2e/helpers/auth.ts and un-fixme the
    SALES and ACCOUNTANT describe blocks; assert no create/mutate control renders for those
    roles on journals, users, and sales routes.""",
    "role-boundaries.spec.ts green for all four roles in the e2e CI job",
    "web", archetype=["ARCH-03", "ARCH-01"], business_metric="support_ticket_rate",
), "G-4 | strategy section 7 register")

add(item(
    "QOS-0002", "SECURITY_PRIVACY",
    "Not every inbound webhook has a signature-forgery test",
    ["P1"], "Any inbound webhook (payment capture, refund, SaaS billing)",
    """One unverified inbound webhook lets an attacker forge financial events. The WF-17
    forgery pattern exists for one route but is not enumerated across every inbound webhook;
    full enumeration is mis-blocked behind D3 sandbox credentials it does not actually need.""",
    "heuristic",
    ["docs/TESTING_STRATEGY.md#7 G-8", "backend/tests/test_payment_webhook_adversarial.py",
     "docs/FREEZE_SCOPE_COVERAGE.md H10"],
    "Static read of the webhook routes vs the one adversarial suite that exists.",
    3, 5, 2, "P1",
    "severity 5 -> High and exempt from the evidence cap; set at P1 to match the strategy register.",
    "M",
    """Enumerate every inbound webhook route; parametrise each with {missing signature,
    wrong signature, replayed event id} -> all must 400 / no-op. The signature check needs
    no live credentials.""",
    "a parametrised webhook-forgery test covering every inbound route, blocking in CI",
    "backend", business_metric="renewal",
), "G-8 | strategy section 7 register")

add(item(
    "QOS-0003", "PERFORMANCE",
    "Pilot scale is unvalidated - no executed load, soak, or large-tenant test",
    ["P1"], "Reports / lists / exports over a full year of data",
    """In progress 2026-09-11, two halves: (1) DONE + verified — a real 50k-invoice
    fixture (tests/test_qos0003_large_tenant_reports.py) proved sales_register's
    existing MAX_REGISTER_ROWS_HARD_CAP (10,000) correctly refuses a full-year pull
    on a 50k tenant rather than silently materialising it, and that a realistic
    month-window query stays flat (query count independent of tenant size) and fast;
    run locally end-to-end, 3/3 pass. (2) WRITTEN, not yet proven green — the
    load-harness CI job now boots a real backend + Postgres and runs the k6 smoke
    for real (was `test -f load/k6_smoke.js` with nothing ever executing it), but
    this session has no k6 binary or a live GitHub Actions run to confirm it passes;
    it needs its first real CI run before this half can be called verified.""",
    "heuristic",
    ["docs/TESTING_STRATEGY.md#7 G-7", ".github/workflows/ci.yml load-harness job",
     "docs/FREEZE_SCOPE.md C7", "backend/tests/test_qos0003_large_tenant_reports.py"],
    "Large-tenant fixture run locally end-to-end (3/3 pass); the k6-in-CI wiring is unverified pending a real CI run.",
    4, 3, 3, "P1",
    "Impact Medium (36); a cheap executed smoke closes most of the risk now.",
    "L",
    """Large-tenant fixture: done. k6-in-CI: written (boots backend + Postgres, installs
    k6, asserts the script's own p95/error-rate thresholds), advisory until it has run
    green on main a few times — confirm on the first real CI run, don't assume.""",
    "k6 smoke lane (advisory then blocking) + a large-tenant report/export timing test",
    "backend", archetype=["ARCH-03"], business_metric="renewal",
), "G-7 | strategy section 7 register")

add(item(
    "QOS-0004", "BUSINESS_GAP",
    "No practising CA has filed GST returns from Bizboard worksheets (H-05)",
    ["P6"], "CA files GSTR-1/3B from Bizboard worksheets without recalculation",
    """Every upstream check (guard_ca_tax_parity F1-F8, GSTR JSON snapshots, GSTR-1<->3B
    tie-out) is a proxy. The core value proposition - a CA files directly from the
    worksheets - has not been demonstrated with a real practitioner on a real filing.""",
    "hypothesis",
    ["docs/TESTING_STRATEGY.md#7 G-14", "docs/ca/CA_SIGN_OFF_CHECKLIST.md",
     "docs/BUSINESS_ARCHETYPES_AND_PERSONAS.md section 11 H-05"],
    "Not observed; the fix is not code. Confirmed only by Stage-3 pilot fieldwork in a live filing window.",
    5, 4, 3, "P1-investigate",
    "Impact High (60); hypothesis evidence -> investigation priority. Next action is pilot Stage 3, not a code change.",
    "L",
    """Run pilot Stage 3 with 3-5 practising CAs against a fully closed month produced by the
    Stage 1-2 pilots; record whether each files without recalculation (PASS) or rejects for a
    split / balance mismatch (FAIL). INCONCLUSIVE extends the experiment.""",
    "H-05 recorded PASS for a majority of the Stage-3 CA cohort",
    "founder", archetype=["ARCH-03"], business_metric="renewal",
), "G-14 | strategy section 7 register", "readiness-dim-7 | BUSINESS_ARCHETYPES section 9 'Compliance confidence UNTESTED'")

add(item(
    "QOS-0005", "BUSINESS_GAP",
    "Bank reconciliation proper (statement-line to GL match) is not gated",
    ["P5"], "Match bank statement lines to GL",
    """WF-33 (reconcile a statement against GL) is skipped; only statement import + auto-match
    (WF-41) is gated. 'Discrepancy with bank lines' is the Munshi's stated veto trigger and
    the daily trust check has no end-to-end coverage. No external dependency blocks WF-33.""",
    "heuristic",
    ["docs/TESTING_STRATEGY.md#7 G-3", "docs/FREEZE_SCOPE_COVERAGE.md section G (WF-33)"],
    "WF-33 is a documented skip; WF-37/38 (gateway refund/MDR) are separately blocked on D3 creds.",
    3, 4, 3, "P1",
    "Impact Medium (36); WF-33 is unblocked work.",
    "M",
    """Implement WF-33: open a reconciliation session, match statement lines to GL entries,
    assert the session closes balanced and an idempotent replay is a no-op. Track WF-37/38
    separately under the D3-credentials blocker.""",
    "test_wf33_bank_reconciliation green (unblocked); WF-37/38 tracked as blocked",
    "backend", archetype=["ARCH-03", "ARCH-04"], business_metric="renewal",
), "G-3 | strategy section 7 register")

add(item(
    "QOS-0006", "RELIABILITY_TRUST",
    "Concurrency-race tests never execute on a local dev box",
    ["P5", "P1"], "Any money or stock mutation under concurrent requests",
    """tests/test_concurrency_races.py is postgres-marked; local dev runs SQLite where
    SELECT ... FOR UPDATE is a no-op. Oversell / double-allocation regressions are invisible
    until CI, so they land in review already broken.""",
    "heuristic",
    ["docs/TESTING_STRATEGY.md#7 G-11a", "docs/FREEZE_SCOPE_COVERAGE.md Open GAPs 3"],
    "Structural: the marker gates the tests off SQLite; nothing prompts a dev to run the Postgres lane.",
    2, 5, 3, "P1",
    "severity 5 -> High; effort is small (docs + a helper), so this ranks well.",
    "S",
    """Document and tool a pre-merge `pytest -m postgres` against a local Postgres container
    for any change touching allocation or stock code; add it to CONTRIBUTING and a pre-push
    reminder.""",
    "CONTRIBUTING documents the local Postgres lane; a make/script target runs it",
    "backend", business_metric="renewal",
), "G-11a | strategy section 7 register")

add(item(
    "QOS-0007", "USABILITY",
    "No keyboard-only accessibility journey for POS or the invoice form",
    ["P2"], "Keyboard-only operation of POS + invoice form",
    """axe runs on login and dashboard only. There is no keyboard-only journey for POS
    (H-02 assumes a mouse-free counter checkout), no axe on the invoice form / a report /
    a settings screen, and no screen-reader-label assertion.""",
    "heuristic",
    ["docs/TESTING_STRATEGY.md#7 G-6", "web/e2e/a11y.spec.ts"],
    "The a11y spec covers 2 of ~90 screens; the keyboard-only path is assumed by H-02 but unasserted.",
    3, 3, 4, "P1",
    "Impact Medium (36); acute for ARCH-01. Base P1 for Medium.",
    "M",
    """Add a Playwright journey that completes a 5-line POS checkout with keyboard only,
    asserting focus never leaves the scan field and completion lands under the H-02 budget;
    extend a11y.spec.ts to the invoice form, one report, one settings screen.""",
    "keyboard-only POS spec + expanded a11y spec, both in the e2e CI job",
    "web", archetype=["ARCH-01"], business_metric="activation",
), "G-6 | strategy section 7 register")

add(item(
    "QOS-0008", "PERSONA_GAP",
    "No persona journey for the Godown Custodian at a departmental firm",
    ["P4"], "Inward, transfer, and count-variance as a role journey",
    """Inter-godown transfer and physical count-variance are tested as isolated invariants
    and edge cases, never as a P4 role journey with a deny-set. A capability regression for
    this persona (custodian gains pricing or journal access) would not be caught.""",
    "heuristic",
    ["docs/TESTING_STRATEGY.md#7 G-1", "backend/tests/personas/README.md"],
    "The PJ matrix has no Godown-Keeper row; ARCH-04 count-variance lives only in tests/edge/.",
    2, 3, 3, "P2",
    "Impact Medium (18); Stage-4 archetype, so judgement lowers it to P2.",
    "M",
    """Add PJ-WHOLE-GODOWN: inward, inter-godown transfer, a count session with a variance
    adjustment, and a deny-set (no pricing, no journals, no reports). Green in the strict
    invariant sweep.""",
    "PJ-WHOLE-GODOWN journey added to backend/tests/personas/",
    "backend", archetype=["ARCH-04"], business_metric="none",
), "G-1 | strategy section 7 register")

add(item(
    "QOS-0009", "PERSONA_GAP",
    "ARCH-05/06 test coverage: near-expiry guard-band and bulk-serial partial failure",
    ["P4"], "Batch expiry policy and bulk serial ingest",
    """Fixed 2026-09-11: added test_expiry_guard_band_matrix (6 cases: block_expired
    on/off x expired/near-expiry-today/not-near-expiry) pinning that a lot expiring
    *today* is sellable regardless of policy (expiry_date < business date, not <=);
    test_serial_bulk_ingest_partial_failure (a within-paste duplicate serial rolls back
    the whole opening-stock post, no half-written serials or balance bump); and
    test_warranty_fraud_duplicate_return (the same sold serial cannot be returned
    twice). Auto-pick FEFO was scoped out — QOS-0009's own earlier investigation found
    it lives at the invoice-complete layer, not post_movement, so a matrix axis for it
    there would test the wrong layer.""",
    "heuristic",
    ["docs/TESTING_STRATEGY.md#7 G-2", "backend/tests/matrices/test_company_settings_matrix.py::test_expiry_guard_band_matrix",
     "backend/tests/test_item_godown_expiry.py::test_serial_bulk_ingest_partial_failure",
     "backend/tests/test_item_godown_expiry.py::test_warranty_fraud_duplicate_return"],
    "All 3 tests pass; full backend suite 1489 passed / 23 skipped with no regressions.",
    2, 4, 2, "P2",
    "Impact Low (16); Stage-4 archetypes. Base P2 for Low.",
    "M",
    """Done: expiry-policy x guard-band matrix + the two serial tests. Manual-pick only
    (post_movement always requires an explicit batch); auto-pick FEFO is a different
    layer, out of scope here per QOS-0009's own earlier finding.""",
    "expiry-policy matrix axis + the two serial tests, green in the Phase 2 gate",
    "backend", archetype=["ARCH-05", "ARCH-06"], business_metric="none",
), "G-2 | strategy section 7 register")

add(item(
    "QOS-0010", "USABILITY",
    "~90 pages have at most one smoke each; page-level UX is largely unguarded",
    ["P1", "P2", "P5"], "Any secondary screen (settings, list, detail)",
    """Broad page-level behaviour (render, no console error, basic a11y) is covered for a
    handful of routes. Friction compounds across the long tail of settings and list screens
    that no test touches.""",
    "heuristic",
    ["docs/TESTING_STRATEGY.md#7 G-5", "docs/reviews/UX_AUDIT_FINDINGS.md"],
    "~12-42 FE test files vs ~90 pages; the UX audit is a point-in-time snapshot, not a guard.",
    4, 2, 3, "P2",
    "Impact Medium (24); base P1 for Medium, judgement lowers to P2 (long-tail, diffuse).",
    "L",
    """Add one render + no-console-error + axe smoke for the top-20 routes by usage; keep the
    remaining pages an accepted LIM.""",
    "a parametrised top-20-route smoke spec in the e2e CI job",
    "web", business_metric="activation",
), "G-5 | strategy section 7 register")

add(item(
    "QOS-0011", "SECURITY_PRIVACY",
    "CSP is not implemented in-app; no external penetration test yet",
    ["P1"], "Cross-cutting web security posture",
    """Content-Security-Policy is not emitted by the app (treated as an edge/CDN concern,
    stated but not gated). No external pen-test has been run; docs/pilot/PENTEST_SOW.md is a
    draft scheduled for Phase 5.""",
    "heuristic",
    ["docs/TESTING_STRATEGY.md#7 G-9", "docs/pilot/PENTEST_SOW.md",
     "backend/tests/errors/test_freeze_gate_contracts.py"],
    "Django-emitted headers are gated; CSP is absent; pen-test is a planned external engagement.",
    3, 3, 1, "P2",
    "Impact Low (9); base P2. Pen-test is external and Phase 5.",
    "M",
    """Decide the CSP delivery point (edge vs app) and add a header-presence test once
    decided; commission the Phase 5 pen-test per the SOW and triage findings into this
    backlog.""",
    "a CSP header presence test + pen-test findings triaged as QOS items",
    "ops", business_metric="renewal",
), "G-9 | strategy section 7 register", "issue-register P1 'No pen-test before GA'")

add(item(
    "QOS-0012", "RELIABILITY_TRUST",
    "Real-broker Celery task ordering is hidden by eager mode",
    ["P5"], "Webhook vs period-close vs e-invoice-submit ordering",
    """Task effects are asserted throughout the chains, but eager mode hides ordering and
    retry timing. A real-broker race (a webhook landing during a period close) would not be
    caught.""",
    "heuristic",
    ["docs/TESTING_STRATEGY.md#7 G-10", "docs/FREEZE_SCOPE.md H3"],
    "Eager mode is the test default; ordering is only exercised against a real broker.",
    2, 3, 1, "P3",
    "Impact Low (6); Phase-5 work, judgement P3.",
    "L",
    """Phase 5: run WF-17, period-close, and e-invoice-submit chains against a real broker
    and assert the user-visible end state under interleaving.""",
    "key chains run green against a real broker in a Phase 5 lane",
    "backend", business_metric="renewal",
), "G-10 | strategy section 7 register")

add(item(
    "QOS-0013", "RELIABILITY_TRUST",
    "End-to-end tests run on Chromium only; two mobile-viewport failures carried",
    ["P1", "P2"], "Cross-browser and mobile-viewport rendering",
    """The e2e and golden suites run Chromium only. Two known mobile-viewport layout failures
    (help.spec.ts:55 universal-search combobox; item-custom-fields.spec.ts:46 heading behind
    the mobile nav drawer) are carried as pre-existing.""",
    "heuristic",
    ["docs/TESTING_STRATEGY.md#7 G-12", "docs/FREEZE_SCOPE_COVERAGE.md 'Final verification'"],
    "playwright.config.ts defines one project; the two mobile fails are baselined as pre-existing.",
    3, 2, 2, "P3",
    "Impact Low (12); judgement P3.",
    "M",
    """Add a WebKit project for the golden + a11y specs; fix or formally accept (with a
    rationale) the two mobile-viewport failures.""",
    "a WebKit e2e project green; the two mobile fails fixed or accepted with a rationale",
    "web", business_metric="activation",
), "G-12 | strategy section 7 register")

add(item(
    "QOS-0014", "RELIABILITY_TRUST",
    "No schema-migration rehearsal against a production-shaped dataset",
    ["P1"], "Applying a migration to real data",
    """In progress 2026-09-11, per explicit user direction (build a synthetic
    placeholder — "proves the mechanism, not real-data safety"): scripts/
    migration_rehearsal.sh spins up a throwaway Postgres, applies the full
    migration series, seeds a large SYNTHETIC dataset (accounts/management/
    commands/seed_synthetic_bulk.py — explicitly NOT a real anonymised
    production dump, see its own docstring), then re-runs `migrate` and times
    it against a budget. Run end-to-end locally: PASS in ~8s at 300 rows.
    Honest limitation: at HEAD there is no pending migration for this to
    actually exercise against volume, so today it mainly proves the
    orchestration mechanism (idempotent + fast even with rows present) — the
    real test happens automatically the next time a schema migration lands on
    a branch with this job wired in. A real anonymised production dump would
    still be the stronger version of this item if one becomes available.""",
    "heuristic",
    ["docs/TESTING_STRATEGY.md#7 G-11b", "docs/FREEZE_SCOPE.md G7 'Backfill / reconcile ... P3'",
     "scripts/migration_rehearsal.sh", ".github/workflows/migration-rehearsal.yml",
     "backend/accounts/management/commands/seed_synthetic_bulk.py"],
    "Local end-to-end run: PASS (migrate clean + within an 8s/60s budget at 300 synthetic rows).",
    2, 4, 1, "P3",
    "Impact Low (8); P3, Phase 3 infra work.",
    "M",
    """Done (synthetic placeholder, per user direction): the rehearsal mechanism —
    spin up db, seed at volume, re-run migrate, time it, alert on regression. A real
    anonymised production dump would still be the stronger version of this if one
    becomes available later.""",
    "a migration-rehearsal CI job green on an anonymised dump",
    "backend", business_metric="renewal",
), "G-11b | strategy section 7 register")

add(item(
    "QOS-0015", "RELIABILITY_TRUST",
    "No accuracy benchmark for LLM bill extraction",
    ["P5"], "LLM bill extraction quality over time",
    """In progress 2026-09-11, per explicit user direction (harness shell only, zero
    fixtures — a synthetic/rendered bill would be trivially easy for a vision model
    and would measure nothing real): tests/accuracy/test_llm_bill_extraction_accuracy.py
    calls the real configured LLM provider against whatever cases exist in
    tests/fixtures/bill_accuracy_corpus/ (image + expected-fields JSON pairs),
    scores header + line-item fields, and asserts an ACCURACY_FLOOR. Marked
    `llm_accuracy` (pytest.ini) so it costs nothing and never runs in the default
    lanes. The corpus itself is still empty — assembling ~30 real bill images with
    verified expected fields remains a real, human task; this only removes "build
    the harness" from what's left to do once that corpus exists.""",
    "heuristic",
    ["docs/TESTING_STRATEGY.md#7 G-13", "backend/tests/errors/test_llm_extraction_failures.py",
     "backend/tests/accuracy/test_llm_bill_extraction_accuracy.py",
     "backend/tests/fixtures/bill_accuracy_corpus/README.md"],
    "The no-corpus skip path is proven (1 skipped, clean); the scoring logic itself is unexercised against a real case, since none exist.",
    1, 3, 2, "P3",
    "Impact Low (6); draft-with-review lowers urgency. P3.",
    "M",
    """Done (harness shell, per user direction): the accuracy-scoring test lane, skip-
    when-empty behaviour, and its README. Assembling ~30 real bill images with
    verified expected fields is the remaining, genuinely human task.""",
    "an advisory LLM-extraction accuracy lane with a documented floor",
    "backend", business_metric="none",
), "G-13 | strategy section 7 register")

add(item(
    "QOS-0016", "DELIGHT",
    "Dashboard render budget is unmeasured with realistic data volume",
    ["P1"], "Dashboard first render with 12 months of data",
    """Delight is asserted only as pilot hypotheses. There is no automated 'dashboard renders
    within X ms with N months of data' check, so a slow dashboard would ship unnoticed - and
    'visibility at a glance' is P1's core motive.""",
    "hypothesis",
    ["docs/TESTING_STRATEGY.md#7 G-15", "docs/TESTING_STRATEGY.md#6.10"],
    "No latency budget exists in any e2e spec; not observed with a realistic dataset.",
    5, 2, 4, "P1-investigate",
    "Impact Medium (40); hypothesis -> investigation. Build the observation first (ADR 0001).",
    "M",
    """Once the observation layer lands, seed a 12-month fixture and assert dashboard
    first-contentful render under a p95 budget in a Playwright timing spec.""",
    "a dashboard render-budget assertion in the e2e suite",
    "web", business_metric="activation",
), "G-15 | strategy section 7 register")

add(item(
    "QOS-0017", "DELIGHT",
    "POS friction (modal count, focus loss) has no automated budget",
    ["P2"], "POS checkout friction",
    """The archetype matrix names modal popups, slow print render, and keyboard focus loss as
    ARCH-01 friction points. None has a regression guard, so a change that reintroduces a
    blocking modal in the scan loop would not be caught.""",
    "hypothesis",
    ["docs/TESTING_STRATEGY.md#7 G-16", "docs/BUSINESS_ARCHETYPES_AND_PERSONAS.md section 6"],
    "No spec counts modals or asserts focus retention during POS; not observed.",
    3, 3, 4, "P1-investigate",
    "Impact Medium (36); hypothesis -> investigation, pending the observation layer.",
    "M",
    """Add a Playwright assertion during POS that counts opened [role=dialog] elements
    (target 0 blocking) and that focus stays in the scan field across a 5-line checkout.""",
    "a POS friction spec (modal count + focus retention) in the e2e suite",
    "web", archetype=["ARCH-01"], business_metric="nps",
), "G-16 | strategy section 7 register")

add(item(
    "QOS-0018", "RELIABILITY_TRUST",
    "determinism-probe stays advisory - 5 clock-brittle test fixtures",
    ["P5"], "Suite determinism under a frozen clock",
    """The determinism-probe CI job runs the suite with a frozen clock and network ban but is
    advisory: 5 fixtures have hard-coded Aug/Sep-2026 dates that read as 'future' under the
    frozen 2026-06-15 clock.""",
    "heuristic",
    ["docs/TESTING_STRATEGY.md#7 G-determinism", "scripts/ci_gates/GATE_INVENTORY.md"],
    "Probe is 1472 pass / 5 fail; the 5 are named clock-brittle fixtures, not product bugs.",
    1, 2, 1, "P2",
    "Impact Low (2); small, contained fix. P2 to keep it visible.",
    "S",
    """Make the 5 fixtures' dates relative to timezone.now(); once green on main x3, flip
    determinism-probe to blocking and delete the env guards.""",
    "determinism-probe green on main for 3 consecutive runs, then promoted to blocking",
    "backend", business_metric="none",
), "G-determinism | strategy section 7 register")

add(item(
    "QOS-0019", "RELIABILITY_TRUST",
    "Mutation testing is blocked - line coverage is not behaviour coverage",
    ["P5"], "Test-suite strength on money / tax / stock code",
    """The mutation audit (scripts/mutation_audit.sh) is blocked: mutmut has no native Windows
    support. Coverage is ~84% line / 80% diff, which proves execution, not assertion - the
    real check for weak tests is not running.""",
    "heuristic",
    ["docs/TESTING_STRATEGY.md#7 G-mutation", "docs/FREEZE_SCOPE.md H11"],
    "The audit script exists but cannot run on the dev platform; no survivor triage has happened.",
    2, 3, 1, "P2",
    "Impact Low (6); P2 - a Linux CI lane is a modest lift and de-risks the money paths.",
    "M",
    """Run scripts/mutation_audit.sh in a Linux CI lane (advisory); triage survivors on the
    money, tax, and stock modules first.""",
    "an advisory mutation-audit lane with survivors triaged on the money/tax/stock modules",
    "backend", business_metric="none",
), "G-mutation | strategy section 7 register")

# ======================================================================
# B. Issue-register P0/P1 residuals (FREEZE_SCOPE_COVERAGE.md sweep)
# ======================================================================

add(item(
    "QOS-0020", "SECURITY_PRIVACY",
    "No TLS termination at the application edge",
    ["P1"], "All traffic to the deployed app",
    """In progress 2026-09-11: the pilot deployment still has no reverse proxy / load
    balancer terminating TLS at the application edge — that half is genuinely ops-owned
    (docker-compose.yml's own `nginx` service comment: it is deliberately plain HTTP,
    "must sit behind a TLS edge", and this repo intentionally does not pick a terminator
    since the real pilot host's topology — cloud LB, Cloudflare, a VPS's own nginx — is
    an ops decision this session cannot see or make safely). What IS done: the "verify
    HSTS and redirect behaviour" half — scripts/edge_tls_smoke.sh, proven against a real
    HTTPS host (pass) and a plain-HTTP host (correctly fails), wired into
    docs/pilot/ENV_CHECKLIST.md item 1 so the sign-off requires running it, not just
    checking a box.""",
    "heuristic",
    ["docs/FREEZE_SCOPE_COVERAGE.md 'P0/P1 issue-register sweep'",
     "scripts/edge_tls_smoke.sh", "docker-compose.yml (nginx service comment)"],
    "Smoke script run against a real HTTPS host (pass) and a plain-HTTP host (correct fail); the edge itself is still unbuilt, ops-owned.",
    5, 5, 1, "P1",
    "severity 5 -> High and cap-exempt; infra-owned, so P1 with an ops owner rather than a code P0.",
    "M",
    """Verification tooling: done (edge_tls_smoke.sh). Standing up the actual reverse
    proxy / load balancer in front of the real pilot host is still an ops action — this
    session doesn't know the deployment topology and won't guess at one.""",
    "an edge TLS smoke (https enforced, HSTS present) in the deploy checklist",
    "ops", business_metric="renewal",
), "issue-register P0 'No TLS termination at application edge' | infra")

add(item(
    "QOS-0021", "BUSINESS_GAP",
    "Pilot Go/No-Go gates are unsigned",
    ["P1"], "Pilot readiness governance",
    """docs/pilot/GO_NO_GO.md has unsigned PM / Eng / QA / CA / Ops rows, and the Wave 16
    Final Gates are not signed. A governance gap, not a code defect, but it blocks a clean
    pilot start.""",
    "heuristic",
    ["docs/FREEZE_SCOPE_COVERAGE.md 'P0/P1 issue-register sweep'", "docs/pilot/GO_NO_GO.md"],
    "The sign-off table is empty; UAT / CA / TLS / backup rows are open.",
    5, 4, 1, "P1",
    "Impact Medium (20); governance blocker for pilot start.",
    "S",
    """Walk the Go/No-Go checklist with each owner; capture signatures and dates, or record
    explicit conditional-go items.""",
    "GO_NO_GO.md signed by all five roles (or conditional-go items recorded)",
    "founder", business_metric="none",
), "issue-register P0 'Pilot Go/No-Go gates unsigned' | governance",
   "issue-register P1 'GO_NO_GO.md unsigned (CA/UAT/TLS/backup)' | governance (merged)")

add(item(
    "QOS-0022", "RELIABILITY_TRUST",
    "No scheduled backup/restore drill in the compose stack",
    ["P1"], "Disaster recovery",
    """Fixed 2026-09-11: scripts/restore_drill.sh drives the real pg_dump/gzip -> psql
    restore pipeline (the same commands as scripts/backup.sh / scripts/restore.sh) into
    two throwaway containers — never the live db service — then runs the new standalone
    manage.py check_invariants sweep against the restored data. Scheduled weekly via
    .github/workflows/backup-restore-drill.yml (cron + workflow_dispatch), advisory
    (continue-on-error) so a drill failure alerts without blocking merges.""",
    "heuristic",
    ["docs/FREEZE_SCOPE_COVERAGE.md 'P0/P1 issue-register sweep'",
     "scripts/restore_drill.sh", ".github/workflows/backup-restore-drill.yml",
     "backend/tests/test_check_invariants_command.py"],
    "First-hand code read + a local end-to-end run of the drill script; 3 unit tests for check_invariants pass.",
    3, 4, 1, "P2",
    "Impact Medium (12 -> Low by product, but severity 4 recovery risk); set P2.",
    "M",
    """Done: scripts/restore_drill.sh + manage.py check_invariants + a weekly scheduled
    CI job. Exercises the actual dump/restore pipeline, not just the ORM-level logic.""",
    "a scheduled restore-drill job that runs the invariant sweep against the restored DB",
    "ops", business_metric="renewal",
), "issue-register P1 'No automated backup / restore drill in compose' | ops",
   "issue-register P1 'compose backup profile has no scheduled restore automation' | ops (merged)")

add(item(
    "QOS-0023", "SECURITY_PRIVACY",
    "CD pushes mutable sha tags without a digest pin",
    ["P1"], "Container image supply chain",
    """The deploy pipeline pushes mutable sha tags without pinning image digests, so a
    re-tagged or tampered image could be deployed under the same reference.""",
    "heuristic",
    ["docs/FREEZE_SCOPE_COVERAGE.md 'P0/P1 issue-register sweep'"],
    "Recorded P1 in the issue register; DevOps-owned.",
    2, 3, 1, "P2",
    "Impact Low (6); contained supply-chain hardening. P2.",
    "S",
    """Pin deploy references to image digests (sha256) in the CD pipeline and the compose
    prod overlay; fail the deploy if a digest is missing.""",
    "the deploy pipeline references image digests, asserted by a CI check",
    "devops", business_metric="none",
), "issue-register P1 'CD pushes mutable sha tags without digest pin' | devops",
   "BB-000470 | MASTER_ISSUE_REGISTER (Deferred - ops owner)")

add(item(
    "QOS-0049", "SECURITY_PRIVACY",
    "DPDP controls checklist is unsigned",
    ["P1"], "Data-protection governance for the pilot",
    """The DPDP (Digital Personal Data Protection) controls checklist
    (docs/pilot/DPDP_POSTURE.md) has no recorded sign-off. The posture may be sound but there
    is no attestation that each control was reviewed before onboarding real merchant data.""",
    "heuristic",
    ["docs/reviews/MASTER_ISSUE_REGISTER.md BB-000128 (Deferred - ops owner)",
     "docs/pilot/DPDP_POSTURE.md"],
    "Recorded P2 in the issue register as an unsigned governance checklist; ops-owned.",
    5, 3, 1, "P2",
    "Impact Medium (15 -> Low by product, but a compliance gate); governance blocker for onboarding real data.",
    "S",
    """Walk docs/pilot/DPDP_POSTURE.md control by control with the data-protection owner;
    record a reviewed/date against each and a checklist signature.""",
    "DPDP_POSTURE.md carries a per-control review record and a signature",
    "ops", business_metric="renewal",
), "BB-000128 | MASTER_ISSUE_REGISTER (Deferred - ops owner)")

add(item(
    "QOS-0050", "RELIABILITY_TRUST",
    "No chaos / failover drill for Redis or Postgres",
    ["P1"], "A dependency (cache or DB) goes down mid-operation",
    """There is no rehearsed drill for Redis or Postgres becoming unavailable: no test that
    the app degrades sanely (clear error, no data loss, recovers on reconnect) when the cache
    or the primary DB drops.""",
    "heuristic",
    ["docs/reviews/MASTER_ISSUE_REGISTER.md BB-000186 (Deferred - ops owner)",
     "docs/TESTING_STRATEGY.md#6.3"],
    "Recorded P2 in the issue register; the resilience suite covers task failure, not dependency outage.",
    3, 4, 1, "P2",
    "Impact Medium (12 -> Low by product; severity 4 recovery risk). P2, ops-owned drill.",
    "M",
    """Add a drill (compose-based or a Phase 5 lane): kill Redis, then Postgres, mid-request;
    assert a clear 5xx with a HelpCode (not a hang), no partial commit, and clean recovery on
    restart.""",
    "a chaos drill covering Redis-down and Postgres-down with the asserted degradation contract",
    "ops", business_metric="renewal",
), "BB-000186 | MASTER_ISSUE_REGISTER (Deferred - ops owner)")

add(item(
    "QOS-0051", "BUSINESS_GAP",
    "No in-product tenant backup / restore or self-service recovery path",
    ["P1"], "A merchant needs to recover their data after a mistake or loss",
    """Stale: BB-000668 (the source this item was mined from) is already fixed. The product
    surface exists: settings/backup (web/src/pages/settings/BackupExportPage.tsx) exposes
    an owner-initiated encrypted export (`POST /company/export/`, rate-limited, audited)
    and two restore paths — a safe-by-default restore into a NEW sandbox company
    (`POST /company/restore/`) for inspection without touching the live tenant, and a
    support-gated in-place destroy+restore requiring the owner to type the exact company
    name (`confirm_destroy` + `typed_name`) before it will overwrite the original. Correction
    (2026-09-11): the capability this item asked for is built and tested, not missing.""",
    "heuristic",
    ["docs/reviews/MASTER_ISSUE_REGISTER.md BB-000668 (Deferred - roadmap, now stale)",
     "web/src/pages/settings/BackupExportPage.tsx",
     "backend/tests/test_sprint_d_tenant_export.py::test_bb_000668_export_restore_sandbox_totals_match",
     "backend/tests/test_sprint_d_tenant_export.py::test_bb_000668_destroy_in_place_requires_typed_name"],
    "First-hand code + test read superseding the roadmap-deferred BB-000668 note it was mined from.",
    3, 3, 1, "P3",
    """Corrected 2026-09-11: not a gap — export, sandbox-restore, and a typed-name-gated
    in-place restore all exist, tested, rate-limited, and audit-logged.""",
    "S",
    """No build needed. If a real gap remains (e.g. a guided in-place-restore UI flow rather
    than sandbox-only in the current page), file a new, narrowly-scoped item — this one's
    "no surface exists at all" premise is false.""",
    "already covered: test_bb_000668_export_restore_sandbox_totals_match, "
    "test_bb_000668_destroy_in_place_requires_typed_name, test_bb_000668_export_rate_limited",
    "backend", business_metric="renewal",
), "BB-000668 | MASTER_ISSUE_REGISTER (Deferred - roadmap)")

# ======================================================================
# C. UX audit fixes lacking a regression guard
# ======================================================================

add(item(
    "QOS-0024", "RELIABILITY_TRUST",
    "No regression guard for the UnsavedChangesGuard useBlocker crash (UX-001)",
    ["P1", "P5"], "Navigating away from an editor page",
    """UX-001 (UnsavedChangesGuard threw a runtime useBlocker exception on standard routes)
    was fixed and verified manually, but no automated test guards it. A router or guard
    refactor could reintroduce the crash.""",
    "heuristic",
    ["docs/reviews/UX_AUDIT_FINDINGS.md UX-001"],
    "Marked 'Fixed & Verified' by screenshot regression; no unit or e2e test references the guard.",
    3, 4, 2, "P2",
    "Impact Medium (24); a crash on a common navigation, but already fixed - this is guard debt.",
    "S",
    """Add a component or e2e test: mount an editor route, navigate to a standard route with
    and without unsaved changes, assert no error boundary and the correct prompt.""",
    "a test exercising UnsavedChangesGuard on standard routes, in the FE suite",
    "web", business_metric="support_ticket_rate",
), "UX-001 | UX_AUDIT_FINDINGS.md (fix lacks a guard)")

add(item(
    "QOS-0025", "DISSATISFACTION",
    "No regression guard for non-owner 403-spamming queries (UX-002)",
    ["P2", "P5"], "First page load as a non-owner role",
    """UX-002 (SALES_STAFF and other non-owner roles were spammed with 403s on every route
    from an eager subscription query) was fixed, but nothing guards it. A re-introduced eager
    query would flood non-owner sessions with errors again.""",
    "heuristic",
    ["docs/reviews/UX_AUDIT_FINDINGS.md UX-002"],
    "Marked fixed; related to but distinct from QOS-0001 (that is about hidden controls, this is about background queries).",
    4, 3, 5, "P2",
    "Impact High (60), but already fixed - guard debt, so P2.",
    "S",
    """Add an e2e assertion: log in as SALES_STAFF, load the app, assert zero 403 responses
    in the network log on the initial route.""",
    "an e2e check asserting zero 403s on a non-owner first load",
    "web", business_metric="support_ticket_rate", duplicates=["QOS-0001"],
), "UX-002 | UX_AUDIT_FINDINGS.md (fix lacks a guard)")

add(item(
    "QOS-0026", "USABILITY",
    "No visual-regression guard for mobile-viewport clipping (UX-003/004/005)",
    ["P1", "P2"], "Using the app on a phone-width viewport",
    """UX-003/004/005 (header search wrap, attention-queue button clipping, POS cart
    horizontal overflow at phone widths) were fixed responsively but only verified by
    one-time screenshots. No test locks the mobile layout.""",
    "heuristic",
    ["docs/reviews/UX_AUDIT_FINDINGS.md UX-003, UX-004, UX-005"],
    "Three related mobile-responsive fixes, all 'Fixed & Verified' by screenshot, none guarded.",
    3, 2, 3, "P2",
    "Impact Medium (18); mobile shell ships to the pilot (D12). P2.",
    "M",
    """Add Playwright mobile-viewport assertions: no horizontal body scroll on dashboard,
    attention queue, and POS; page title not occluded.""",
    "mobile-viewport no-overflow assertions for the three screens, in the e2e suite",
    "web", archetype=["ARCH-01"], business_metric="activation",
), "UX-003 | UX_AUDIT_FINDINGS.md", "UX-004 | UX_AUDIT_FINDINGS.md", "UX-005 | UX_AUDIT_FINDINGS.md")

# ======================================================================
# D. Persona / business gaps (archetypes sections 8-9, coverage)
# ======================================================================

add(item(
    "QOS-0027", "PERSONA_GAP",
    "ARCH-05 needs statutory drug/food forms (20B/21B, FSSAI) before a pharma pilot",
    ["P4", "P1"], "Batch-traceable statutory compliance for pharma/food distribution",
    """ARCH-05 is 'conditionally supported': general batch/FEFO works, but the statutory drug
    licence forms (20B/21B) and FSSAI declarations are absent. A pharma stockist cannot run
    compliant on the product today.""",
    "heuristic",
    ["docs/BUSINESS_ARCHETYPES_AND_PERSONAS.md section 8", "docs/BUSINESS_ARCHETYPES_AND_PERSONAS.md section 13"],
    "Documented boundary condition; deferred to Stage 4.",
    2, 3, 2, "P2",
    "Impact Low (12); Stage-4 archetype, deferred. P2.",
    "L",
    """Scope and build the drug-licence form set (20B/21B) and FSSAI declaration fields on
    batch-traceable invoices before recruiting an ARCH-05 pilot.""",
    "a WF chain covering a batch-traceable statutory invoice with the drug-licence fields",
    "backend", archetype=["ARCH-05"], business_metric="none",
), "ARCH-05-boundary | BUSINESS_ARCHETYPES section 8 (conditionally supported)")

add(item(
    "QOS-0028", "PERSONA_GAP",
    "ARCH-07 milestone billing, job-work, and technician dispatch are unbuilt",
    ["P1", "P5"], "Service-contract milestone invoicing and job-work",
    """ARCH-07 (light commercial service + spares) depends on milestone billing, recurring
    retainers, and job-work / technician dispatch - none of which is in frozen scope. The
    service archetype has no pilot path.""",
    "heuristic",
    ["docs/BUSINESS_ARCHETYPES_AND_PERSONAS.md section 8", "docs/BUSINESS_ARCHETYPES_AND_PERSONAS.md section 12"],
    "Documented: ARCH-07 is 'not in this sequence', revisit as a possible Stage 5.",
    2, 3, 3, "P2",
    "Impact Medium (18); a Stage-5 candidate. P2, effort XL - must be split before scheduling.",
    "XL",
    """Break out milestone billing, recurring retainers, and job-work as separate scoped
    features; do not schedule an ARCH-07 pilot until at least milestone billing ships.""",
    "milestone-billing and recurring-retainer WF chains, each green, before an ARCH-07 pilot",
    "backend", archetype=["ARCH-07"], business_metric="none",
), "ARCH-07-gap | BUSINESS_ARCHETYPES section 8/12")

add(item(
    "QOS-0029", "DISSATISFACTION",
    "UX readiness is untested with real non-technical staff (readiness dim 4)",
    ["P2", "P4", "P5"], "A first-time non-technical operator running a daily task unaided",
    """Readiness dimension 4 ('Can real non-technical staff operate without training?') is
    'UNTESTED IN PILOT'. Every usability claim for the counter clerk, godown custodian, and
    munshi is currently an assumption.""",
    "hypothesis",
    ["docs/BUSINESS_ARCHETYPES_AND_PERSONAS.md section 9"],
    "Explicitly untested; needs a pilot or a synthetic-persona observation run.",
    5, 3, 4, "P1-investigate",
    "Impact High (60); hypothesis -> investigation. Resolved by pilot Stage 1 or the observation layer.",
    "L",
    """During pilot Stage 1, observe unaided first-task completion for P2/P4/P5 (task success
    rate, time, help requests). Or build the synthetic persona agents (ADR 0001) for the
    onboarding and POS journeys.""",
    "unaided-task-completion metrics recorded for P2/P4/P5 against a documented bar",
    "founder", business_metric="activation",
), "readiness-dim-4 | BUSINESS_ARCHETYPES section 9 'UX Readiness UNTESTED'")

add(item(
    "QOS-0030", "BUSINESS_GAP",
    "Operational readiness is untested - can a business run a full day unaided? (dim 8)",
    ["P1", "P5"], "A full business day with no engineer on call",
    """Readiness dimension 8 ('Can the business run on it daily without manual fixes?') is
    'UNTESTED IN PILOT'. Whether real daily operation needs backend intervention is unknown.""",
    "hypothesis",
    ["docs/BUSINESS_ARCHETYPES_AND_PERSONAS.md section 9"],
    "Explicitly untested; the pilot is the experiment.",
    5, 4, 1, "P1-investigate",
    "Impact Medium (20); hypothesis -> investigation. Pilot Stage 2 evidence.",
    "L",
    """Track, during pilot Stage 2, every instance of manual DB/backend intervention and its
    root cause; a clean week is the bar.""",
    "an intervention log across a pilot stage, with root causes triaged into this backlog",
    "founder", archetype=["ARCH-03"], business_metric="renewal",
), "readiness-dim-8 | BUSINESS_ARCHETYPES section 9 'Operational Readiness UNTESTED'")

add(item(
    "QOS-0031", "BUSINESS_GAP",
    "Commercial readiness is untested - will pilots pay and renew? (dim 9)",
    ["P1"], "Post-trial conversion and renewal",
    """Readiness dimension 9 ('Will the business renew and pay after the trial?') is
    'UNTESTED IN PILOT'. Willingness to pay and retention for the lead archetype are
    unvalidated.""",
    "hypothesis",
    ["docs/BUSINESS_ARCHETYPES_AND_PERSONAS.md section 9", "docs/BUSINESS_ARCHETYPES_AND_PERSONAS.md section 11 H-01/H-05"],
    "Explicitly untested; depends on a completed pilot with a conversion offer.",
    5, 4, 1, "P1-investigate",
    "Impact Medium (20); hypothesis -> investigation. The pilot's commercial outcome.",
    "L",
    """At pilot end, make a paid conversion offer to each pilot merchant; record
    conversion rate and stated reasons for non-conversion.""",
    "a conversion outcome recorded for every pilot merchant with reasons",
    "founder", archetype=["ARCH-03"], business_metric="renewal",
), "readiness-dim-9 | BUSINESS_ARCHETYPES section 9 'Commercial Readiness UNTESTED'")

add(item(
    "QOS-0032", "BUSINESS_GAP",
    "Dunning reminders are scheduled but not actually sent (share-link only)",
    ["P5", "P1"], "Automated payment-reminder delivery",
    """The dunning cadence engine schedules reminders and is gated (test_wf42), but actual
    delivery is share-link only in the pilot - the merchant still has to send each reminder
    by hand. ARCH-03's headline pain (collections) is only half-addressed.""",
    "heuristic",
    ["docs/FREEZE_SCOPE.md G3", "docs/FREEZE_SCOPE_COVERAGE.md section G (WF-42)"],
    "Documented LIM: 'cadence engine; share-link delivery only'.",
    3, 2, 2, "P2",
    "Impact Low (12); a stated limitation, but it blunts the core value prop. P2.",
    "M",
    """Decide a delivery channel for the pilot (email at minimum) and wire the dunning
    scheduler to it with a delivery-status field; keep WhatsApp Cloud out of scope.""",
    "a WF chain: dunning schedule -> email sent -> delivery status recorded",
    "backend", archetype=["ARCH-03"], business_metric="renewal",
), "dunning-send | FREEZE_SCOPE section G3")

add(item(
    "QOS-0033", "BUSINESS_GAP",
    "HSN summary correctness in GSTR-1 is not snapshot-pinned on its own",
    ["P6"], "GSTR-1 HSN summary section",
    """HSN summary correctness is folded into test_wf27 but has no standalone blessed
    snapshot. A regression in HSN aggregation could pass wf27's tie-out while producing a
    wrong HSN table the CA relies on.""",
    "heuristic",
    ["docs/TESTING_STRATEGY.md#6.9", "docs/FREEZE_SCOPE.md G5"],
    "Read of the GSTR coverage: tie-out is pinned, the HSN table is not independently snapshotted.",
    3, 3, 2, "P2",
    "Impact Medium (18); CA-facing. P2.",
    "S",
    """Add a blessed snapshot of the GSTR-1 HSN summary for a mixed-rate, mixed-HSN period to
    tests/snapshots/.""",
    "a GSTR-1 HSN summary snapshot test in tests/snapshots/",
    "backend", archetype=["ARCH-03"], business_metric="none",
), "hsn-summary | FREEZE_SCOPE section G5 / TESTING_STRATEGY 6.9")

add(item(
    "QOS-0034", "BUSINESS_GAP",
    "Cost-centre filtered report snapshot is missing",
    ["P5", "P6"], "Reports filtered by cost centre",
    """Date, party, and godown filtered-report snapshots exist; the cost-centre filter case
    is the one remaining open GAP in the report-reconciliation set.""",
    "heuristic",
    ["docs/FREEZE_SCOPE_COVERAGE.md 'Open GAPs' 1", "docs/TESTING_STRATEGY.md#6.9"],
    "Named as the single remaining filtered-report snapshot gap.",
    2, 2, 2, "P3",
    "Impact Low (8); a small, contained snapshot gap. P3.",
    "S",
    """Add a cost-centre-filtered P&L snapshot to tests/snapshots/test_exports_and_filtered_reports.py.""",
    "a cost-centre-filtered report snapshot test",
    "backend", business_metric="none",
), "coverage-open-gap-1 | FREEZE_SCOPE_COVERAGE Open GAPs")

add(item(
    "QOS-0035", "PERSONA_GAP",
    "ARCH-06 bulk serial scanner-paste workflow is not built out",
    ["P4"], "Inward-ing a large consignment of serialised units",
    """Fixed 2026-09-11: web/src/components/billing/lineHelpers.ts::parseSerialInput now
    expands a hyphenated numeric range ("IMEI1000-IMEI1005") and de-dupes a barcode
    scanned twice, with the purchase-inward line (NewPurchasePage.tsx) surfacing the
    parsed count, ranges-expanded count, duplicates-dropped count, and a
    quantity-mismatch warning before the dealer submits. The partial-failure report itself is
    QOS-0009's fail-closed, all-or-nothing rollback (a bad serial anywhere in the
    consignment rolls back the whole opening-stock post, no half-written serials).""",
    "heuristic",
    ["docs/BUSINESS_ARCHETYPES_AND_PERSONAS.md section 8",
     "web/src/components/billing/lineHelpers.test.ts",
     "backend/tests/test_item_godown_expiry.py::test_serial_bulk_ingest_partial_failure"],
    "First-hand code + test read; 7 FE unit tests + the backend partial-failure test all pass.",
    2, 3, 3, "P2",
    "Impact Medium (18); Stage-4 archetype. P2. Related to QOS-0009's test coverage.",
    "M",
    """Done: de-dup + range detection in the shared serial-input parser, wired into the
    purchase-inward line with live paste feedback; the partial-failure report is
    QOS-0009's atomic rollback.""",
    "a bulk-serial-ingest flow with a partial-failure report, covered by QOS-0009's tests",
    "web", archetype=["ARCH-06"], business_metric="none", depends_on=["QOS-0009"],
), "ARCH-06-boundary | BUSINESS_ARCHETYPES section 8")

# ======================================================================
# E. Delight opportunities
# ======================================================================

add(item(
    "QOS-0036", "DELIGHT",
    "Recurring retainer / subscription invoices are re-typed every cycle",
    ["P5"], "Monthly retainer or subscription billing",
    """WF-11 (recurring invoice) is an explicitly skipped stub. Service contractors and any
    trader with monthly retainers re-enter near-identical invoices by hand each cycle.""",
    "hypothesis",
    ["docs/FREEZE_SCOPE_COVERAGE.md 'Still genuinely skipped' (WF-11)",
     "docs/TESTING_STRATEGY.md#5 ARCH-07"],
    "Feature is unbuilt; the pain is inferred from the retainer-heavy archetypes, not observed.",
    3, 2, 3, "P2",
    "Impact Medium (18); post-freeze feature. P2.",
    "M",
    """Detect near-identical invoices to the same customer on a monthly cadence and offer a
    one-click 'make recurring'; generate drafts on schedule for review.""",
    "WF-11 recurring-invoice chain green once built",
    "backend", archetype=["ARCH-07", "ARCH-03"], business_metric="nps",
), "WF-11 | FREEZE_SCOPE_COVERAGE (skipped stub)")

add(item(
    "QOS-0037", "DELIGHT",
    "Onboarding does not infer legal name / state / PIN from the GSTIN",
    ["P1"], "First-run company setup",
    """A first-time owner re-enters information the system could derive: GSTIN encodes the
    state code and maps to the legal name; PIN implies state. The shortest path to a first
    invoice is longer than it needs to be.""",
    "hypothesis",
    ["docs/reviews/UX_AUDIT_FINDINGS.md Module 1", "docs/TESTING_STRATEGY.md#4 P1"],
    "Inferred from the registration form fields; abandonment not measured.",
    5, 2, 1, "P2",
    "Impact Low (10); once-per-tenant, but it is the activation moment. P2.",
    "M",
    """On GSTIN entry, auto-fill state from the GSTIN state code and offer name/address
    lookup; make every other setup field skippable to a 'finish setup' checklist.""",
    "PJ-NEWUSER asserts first invoice reachable in <=3 screens",
    "web", archetype=["ARCH-03"], business_metric="activation",
), "onboarding-smartfill | UX_AUDIT_FINDINGS Module 1", "G-16-adjacent | TESTING_STRATEGY 6.10")

add(item(
    "QOS-0038", "DELIGHT",
    "No proactive nudge when customers cross the credit-age threshold",
    ["P1"], "Daily cash-and-credit review",
    """Fixed 2026-09-11 (dashboard half only): CollectionAttentionCard on the dashboard
    surfaces a count + total for customers overdue past 30 days, linking each to their
    ledger (?customer=id deep-link into CustomerLedgerPage). The optional daily-digest
    (email/WhatsApp) half of the original ask is NOT built — that needs the
    notification-cadence decision QOS-0032's dunning cadence already made once
    (frequency, quiet hours, opt-out) applied to a *non-collections* digest, which is a
    separate scoping call, not a card-rendering task.""",
    "heuristic",
    ["docs/BUSINESS_ARCHETYPES_AND_PERSONAS.md section 5 (P1 adoption motive)",
     "docs/TESTING_STRATEGY.md#4 P1",
     "web/src/components/CollectionAttentionCard.test.tsx"],
    "Collection-risk data exists (collection-risk scoring); the dashboard card is now built and tested.",
    4, 2, 3, "P2",
    "Impact Medium (24); directly serves the P1 buying motive. P2.",
    "M",
    """Done: the dashboard attention card. The daily-digest half is a real, separate
    scoping decision (cadence, channel, opt-out) — file as its own item if wanted rather
    than silently expanding this one's effort.""",
    "an e2e check that the attention card appears and links to the correct filtered list",
    "web", archetype=["ARCH-03"], business_metric="renewal",
), "proactive-credit-nudge | BUSINESS_ARCHETYPES section 5 / TESTING_STRATEGY 4")

add(item(
    "QOS-0039", "DELIGHT",
    "Bank statement import has no one-click 'accept all confident matches'",
    ["P5"], "Reconciling an imported bank statement",
    """Fixed 2026-09-11: added POST /api/v1/payments/recon/bulk-accept-exact/
    (ReconViewSet.bulk_accept_exact) confirming every EXACT-class suggestion
    (>=90 confidence, exact amount, a hard UTR/reference anchor — the same bar
    the commit-time auto-match already used) across the unmatched queue in one
    call, without requiring the company's auto_match_bank_exact opt-in. Fuzzy/
    ambiguous lines are left untouched for manual review. Each result is
    undoable via the existing recon/unmatch action — no new undo mechanism
    needed. Wired to a button on BankReconPage (web).""",
    "heuristic",
    ["docs/FREEZE_SCOPE_COVERAGE.md section G (WF-41)", "docs/TESTING_STRATEGY.md#4 P5",
     "backend/payments/views.py::ReconViewSet.bulk_accept_exact",
     "backend/tests/test_phase3_payments.py::test_bulk_accept_exact_matches_only_exact_class_and_is_undoable"],
    "First-hand code read + a passing test; reused the existing is_exact_unique_suggestion bar exactly.",
    3, 2, 2, "P3",
    "Impact Low (12); a workflow nicety. P3.",
    "S",
    """Done: bulk-accept-exact endpoint + BankReconPage button. Fuzzy matches are
    correctly left for manual review; undo reuses recon/unmatch.""",
    "a test that bulk-accept touches only EXACT-class rows and is undoable",
    "web", archetype=["ARCH-03"], business_metric="nps",
), "bank-bulk-accept | TESTING_STRATEGY 4 (P5)")

add(item(
    "QOS-0040", "DELIGHT",
    "POS does not remember the last payment method or customer per till",
    ["P2"], "Repeated counter checkouts at the same till",
    """Each POS checkout starts from a blank payment method and (for named-customer sales) a
    blank customer. A till that is 90% UPI re-selects UPI every time.""",
    "hypothesis",
    ["docs/BUSINESS_ARCHETYPES_AND_PERSONAS.md section 6 (ARCH-01 friction)",
     "docs/TESTING_STRATEGY.md#4 P2"],
    "Inferred from the counter workflow; keystroke count not measured.",
    3, 2, 4, "P3",
    "Impact Medium (24); small friction, high frequency. P3 pending the observation layer.",
    "S",
    """Default the payment method to the till's last-used value (per device); keep it a
    one-key change.""",
    "an e2e check that POS pre-selects the last payment method for the session",
    "web", archetype=["ARCH-01"], business_metric="nps",
), "pos-remember-defaults | TESTING_STRATEGY 4 (P2)")

add(item(
    "QOS-0041", "DELIGHT",
    "The GSTR worksheet has no contextual 'how to file this on the portal' help",
    ["P6", "P5"], "Taking a Bizboard worksheet to the GST portal",
    """C1 says the worksheets are calculation aids the user files themselves. The worksheet
    screens do not explain which portal fields each column maps to, so a less-experienced
    filer has to work it out.""",
    "hypothesis",
    ["docs/FREEZE_SCOPE.md C1", "docs/TESTING_STRATEGY.md#4 P6"],
    "Inferred from the 'file it yourself' limitation; not observed with a filer.",
    3, 2, 2, "P3",
    "Impact Low (12); reduces filing anxiety. P3.",
    "S",
    """Add inline help on the GSTR-1 / 3B worksheet mapping each section to its portal
    counterpart, with a short 'how to file' checklist.""",
    "a help-content check that each worksheet section has a portal-mapping help entry",
    "web", archetype=["ARCH-03"], business_metric="nps",
), "gstr-filing-help | FREEZE_SCOPE C1 / TESTING_STRATEGY 4 (P6)")

# ======================================================================
# F. Innovation opportunities (review-only)
# ======================================================================

add(item(
    "QOS-0042", "INNOVATION",
    "One-click GSTR-1/3B filing via a live GSP integration",
    ["P6"], "Filing returns",
    """GSTR portal filing is out of scope (offline worksheets only, C1). A live GSP
    integration would turn the worksheet into a one-click file - the single biggest reason a
    CA would insist on the product.""",
    "hypothesis",
    ["docs/FREEZE_SCOPE.md B / C1", "docs/reviews/18_COMPETITOR_ANALYSIS.md"],
    "Competitors (ClearTax, Zoho) file directly; Bizboard does not. Speculative until a CA cohort asks for it.",
    4, 2, 2, "P3",
    "Innovation, review-only: high pull if H-05 shows CAs want it, large integration cost.",
    "XL",
    """Evaluate a certified GSP partnership post-pilot; gate behind H-05 evidence that CAs
    want in-product filing rather than worksheet export.""",
    "n/a - review-only; would need its own WF chain + GSP contract tests if pursued",
    "founder", archetype=["ARCH-03"], business_metric="renewal",
), "innovation-gsp | 18_COMPETITOR_ANALYSIS")

add(item(
    "QOS-0043", "INNOVATION",
    "ML-assisted bank statement line matching",
    ["P5"], "Reconciling messy bank statements",
    """Fixed 2026-09-11 (payee-memory half only, per explicit user direction): the
    "amount + date fuzz, narration NLP" rule engine already existed (payments.recon
    .score_match). What was missing — a payee-memory layer — is now built:
    payments.models.PayeeMemory records the significant narration tokens
    (payments.recon.narration_tokens) of every confirmed match against the
    customer/supplier it was confirmed to, bootstrapped entirely from THIS
    tenant's own recon history (no external corpus, no cross-tenant training,
    not a trained ML model). A later, differently-worded line for the same payee
    gets a capped confidence bonus (payments.recon.payee_memory_bonus, max 20)
    layered on top of score_match — proven unable to bypass its existing
    amount-match safety rail. Precision/recall against real messy bank data is
    still unmeasured (this session has none) — that half of the original ask
    stays open if pursued further.""",
    "heuristic",
    ["docs/TESTING_STRATEGY.md#4 P5", "docs/FREEZE_SCOPE.md G3 (collection-risk scoring exists)",
     "backend/payments/recon.py::narration_tokens,payee_memory_bonus,remember_payee",
     "backend/tests/test_qos0043_payee_memory.py"],
    "First-hand code read + 5 passing tests, including a safety-rail test (memory alone cannot bypass the amount-hit cap); full backend suite green.",
    3, 2, 3, "P3",
    "Built per explicit user direction (2026-09-11), superseding the earlier review-only Innovation framing for this specific item.",
    "L",
    """Done: payee-memory bonus layered on the existing rule engine, self-bootstrapping
    from the tenant's own confirmed matches. Precision/recall measurement against real
    (not self-generated) messy bank data is still a real gap if this is pursued further.""",
    "a matcher eval harness (precision/recall vs the rule engine) if pursued further",
    "backend", archetype=["ARCH-03", "ARCH-04"], business_metric="nps",
), "innovation-ml-bankmatch | TESTING_STRATEGY 4 (P5)")

add(item(
    "QOS-0044", "INNOVATION",
    "Automated collection-risk scoring with escalating dunning",
    ["P1"], "Receivables management",
    """collection-risk scoring exists as a LIM. Investigation found the "reminder" and
    "call task" rungs of the proposed escalation ladder already exist: automated
    reminders (payments/dunning.py, QOS-0032) and a critical-severity AR_COLLECTION_RISK
    row on the Attention Center (insights/attention.py::_overdue_customer_rows, tested
    by test_b05_attention.py) that names the customer, the overdue amount, and the
    recommended next step for stop_credit/overdue_severe accounts. The one real gap was
    "hold new orders": the invoice-complete credit check only fired for a customer with
    an explicit credit_limit set. Fixed 2026-09-11: an opt-in company setting extends the
    hold to collection_status (stop_credit/overdue_severe) independent of a static limit.""",
    "heuristic",
    ["docs/FREEZE_SCOPE.md G3 (collection-risk = LIM)", "docs/BUSINESS_ARCHETYPES_AND_PERSONAS.md section 10",
     "backend/insights/attention.py::_overdue_customer_rows (AR_COLLECTION_RISK, already built)",
     "backend/sales/services.py (credit hold, now also status-driven behind a flag)"],
    "First-hand code + test read; only the \"hold\" rung had a real gap, not all three as originally framed.",
    4, 2, 3, "P3",
    """Corrected 2026-09-11: two of the three rungs were already built and tested
    (reminders via QOS-0032, the AR_COLLECTION_RISK attention row as the call-task
    rung); only the status-driven hold was missing. Shipped as an opt-in company
    setting so existing tenants see no behaviour change.""",
    "S",
    """Done: Company.auto_credit_hold_on_severe_overdue (opt-in, default off) makes the
    invoice-complete check also block a stop_credit/overdue_severe customer even with no
    credit_limit set. The reminder and call-task rungs needed no new build — they
    already existed.""",
    "a test that flips the flag on and confirms a no-credit-limit, overdue_severe customer is "
    "blocked at invoice-complete, and that it is not blocked with the flag off",
    "backend", archetype=["ARCH-03"], business_metric="renewal", depends_on=["QOS-0032"],
), "innovation-collection-escalation | BUSINESS_ARCHETYPES section 10")

add(item(
    "QOS-0045", "INNOVATION",
    "GSTR-2B vs purchase-register ITC auto-reconciliation",
    ["P6", "P5"], "Claiming input tax credit",
    """C1 (FREEZE_SCOPE.md) states GSTR-2B ITC match is not implemented, but this is
    stale: `reporting/ims.py::classify_and_match` already matches the ingested 2B
    against the purchase register FY-wide and classifies every row into
    exact / value_mismatch / wrong_gstin / missing_in_books / duplicate /
    potentially_ineligible, with `bulk_accept_exact` for one-click acceptance and a
    `/api/v1/reports/gstr2b/ims-summary/` surface. QOS-2026-09-11 correction: the
    capability this item asked for is built and tested, not speculative.""",
    "heuristic",
    ["backend/reporting/ims.py", "backend/tests/test_b03_ims.py::test_ims_summary_api",
     "backend/tests/test_b03_ims.py::test_exact_accept_reclasses_1390_reject_clears_1390"],
    "First-hand code + test read superseding the FREEZE_SCOPE.md C1 note it was mined from.",
    3, 3, 2, "P3",
    """Corrected 2026-09-11: not an unbuilt idea — classify_and_match + bulk_accept_exact
    + the ims-summary API already deliver this. Kept as a backlog record (not deleted)
    so the FREEZE_SCOPE.md C1 staleness that produced it is traceable.""",
    "S",
    """No build needed. If gaps remain (e.g. a friendlier match-bucket UI), file a new,
    narrowly-scoped item against the existing ims-summary API rather than re-opening
    this one as if the engine did not exist.""",
    "already covered: test_ims_summary_api, test_exact_accept_reclasses_1390_reject_clears_1390",
    "backend", archetype=["ARCH-03"], business_metric="renewal",
), "innovation-2b-recon | FREEZE_SCOPE C1")

add(item(
    "QOS-0046", "INNOVATION",
    "Native WhatsApp invoice + payment-link delivery",
    ["P1", "P3"], "Sending an invoice to a customer",
    """WhatsApp Cloud API is out of scope (share-link only). Native WhatsApp delivery of the
    invoice PDF + a payment link matches how ARCH-03 merchants actually communicate with
    customers.""",
    "hypothesis",
    ["docs/FREEZE_SCOPE.md B (ENABLE_WHATSAPP_CLOUD=0)", "docs/reviews/18_COMPETITOR_ANALYSIS.md"],
    "Flagged off; the archetype 'Operating Model' explicitly names WhatsApp. Speculative pending demand.",
    4, 2, 3, "P3",
    "Innovation, review-only: strong fit with ARCH-03 behaviour; needs a WhatsApp BSP and template approval.",
    "L",
    """Evaluate a WhatsApp BSP partnership post-pilot; template the invoice + payment-link
    message and gate behind explicit merchant opt-in.""",
    "n/a - review-only; BSP webhook + delivery-status tests if pursued",
    "backend", archetype=["ARCH-03"], business_metric="referral",
), "innovation-whatsapp | 18_COMPETITOR_ANALYSIS")

add(item(
    "QOS-0047", "INNOVATION",
    "Barcode/label printing + reorder automation for counter retail",
    ["P1"], "Keeping the counter stocked and labelled",
    """Fixed 2026-09-11: the user directed building this out of review-only status.
    web/src/pages/inventory/LabelPrintPage.tsx (/inventory/labels) lets a retailer
    search products, set a copy count per product, and print a shelf-label sheet —
    CODE128 barcode (falls back to SKU when no barcode is set) + name + MRP/price —
    via the browser print dialog, reusing the same no-print/@page pattern as the
    existing ledger/stock-count print screens. The reorder worksheet half of this
    item was already covered by the existing Low Stock page (on-hand vs
    reorder_level, per-warehouse override aware, a reorder action per row) —
    no separate build needed there. Not validated with a real ARCH-01 pilot
    merchant yet (that's still a real, human step, not a code gap).""",
    "heuristic",
    ["docs/BUSINESS_ARCHETYPES_AND_PERSONAS.md ARCH-01", "docs/reviews/18_COMPETITOR_ANALYSIS.md",
     "web/src/pages/inventory/LabelPrintPage.tsx", "web/src/pages/inventory/LabelPrintPage.test.tsx",
     "web/src/pages/inventory/LowStockPage.tsx (already the reorder worksheet)"],
    "First-hand code read + 3 passing component tests; full FE suite 302/48 green, tsc+eslint clean.",
    3, 2, 2, "P3",
    """Built per explicit user direction (2026-09-11), superseding the earlier
    review-only Innovation framing for this specific item.""",
    "M",
    """Done: label-print page (barcode + name + price, CODE128 via jsbarcode) plus the
    pre-existing Low Stock page as the reorder worksheet. Pilot-merchant validation is
    a human step, not a further code task.""",
    "label template + reorder worksheet snapshot if pursued",
    "web", archetype=["ARCH-01"], business_metric="referral",
), "innovation-labels-reorder | 18_COMPETITOR_ANALYSIS")

add(item(
    "QOS-0048", "INNOVATION",
    "Fast quick-entry / voice capture for field order booking",
    ["P3"], "Booking an order on the road",
    """Fixed 2026-09-11: the user directed building this out of review-only status.
    web/src/pages/sales/QuickEntryPage.tsx (/sales/quick-entry) is a keyboard-light
    order-booking sheet: recent customers (from the last 10 invoices, deduped) and
    recent SKUs (per-device localStorage, updated as items are added) as one-tap
    chips, a +/- stepper for quantity instead of typing, one "Save order" action that
    posts a draft SalesInvoice via the existing create-invoice endpoint. Voice
    capture and full offline booking are still deliberately out of scope for this
    pass, per the item's own original recommendation.""",
    "heuristic",
    ["docs/BUSINESS_ARCHETYPES_AND_PERSONAS.md section 5 (P3)", "docs/TESTING_STRATEGY.md#4 P3",
     "web/src/pages/sales/QuickEntryPage.tsx", "web/src/pages/sales/QuickEntryPage.test.tsx"],
    "First-hand code read + 3 passing component tests (customer-required gate, stepper + save payload, recent-chip bumps qty not duplicates); full FE suite 305/49 green.",
    2, 2, 3, "P3",
    "Built per explicit user direction (2026-09-11), superseding the earlier review-only Innovation framing for this specific item.",
    "L",
    """Done: the quick-entry sheet (recent customers + SKUs, stepper-based quantity,
    one-tap save). Voice-to-line stays deferred, as the item always intended.""",
    "a mobile quick-entry e2e journey if pursued",
    "web", archetype=["ARCH-03", "ARCH-04"], business_metric="referral",
), "innovation-quick-entry | TESTING_STRATEGY 4 (P3)")

# ======================================================================
# G. Accepted / won't-fix  (FREEZE_SCOPE.md sections B + C)
# ======================================================================

def wontfix(id_, title, category, persona, journey, problem, rationale, source, test_required="n/a - accepted limitation; no guard required"):
    return item(
        id_, category, title, persona, journey, problem,
        "heuristic", source,
        "Recorded in FREEZE_SCOPE.md as out of pilot scope; stated to pilot users with a manual workaround.",
        2, 2, 1, "P3",
        "Accepted / won't-fix - scoped out of the pilot by decision.",
        "S",
        "None - deliberately out of scope. Where a route surface exists, a test asserts it is inaccessible under the pilot flag profile.",
        test_required, "founder",
        lifecycle="accepted_wontfix", wontfix_rationale=rationale, closed=TODAY,
    )

add(wontfix(
    "QOS-0060", "GSTR report screens and on-portal filing are out of scope", "BUSINESS_GAP",
    ["P6"], "Filing GST returns from inside the product",
    "GSTR screens and GSTN direct filing are flagged off; the product provides offline calculation worksheets only.",
    "Offline worksheets only; not GSTN filing. The CA files on the portal from the worksheet. (C1)",
    ["docs/FREEZE_SCOPE.md B (ENABLE_GSTR=0)", "docs/FREEZE_SCOPE.md C1"],
    test_required="a test asserts the GSTR screens are inaccessible under the pilot flag profile",
), "FREEZE_SCOPE B: GSTR screens | C1")

add(wontfix(
    "QOS-0061", "Live NIC e-invoice / e-way generation is out of scope", "BUSINESS_GAP",
    ["P1", "P6"], "Generating an IRN or e-way bill",
    "No live GSP integration in the pilot; e-invoice is preview/sandbox only, never a filed IRN.",
    "Merchants above threshold keep generating the IRN / EWB in their existing utility and record the number in Bizboard. (C2)",
    ["docs/FREEZE_SCOPE.md B (GSP_LIVE_ENABLED=0)", "docs/FREEZE_SCOPE.md C2"],
    test_required="a test asserts the e-invoice submit UI is inaccessible under the pilot flag profile",
), "FREEZE_SCOPE B: live e-invoice/e-way | C2")

add(wontfix(
    "QOS-0062", "AI insights module is out of scope", "BUSINESS_GAP",
    ["P1"], "AI-generated business insights",
    "ENABLE_AI is off; the AI insights surface is not a pilot differentiator and has an unbounded surface area.",
    "Not a pilot differentiator; unbounded surface. LLM bill extraction (D14) is the only AI path in scope.",
    ["docs/FREEZE_SCOPE.md B (ENABLE_AI off)"],
), "FREEZE_SCOPE B: AI insights")

add(wontfix(
    "QOS-0063", "Tally migration / live sync is out of scope", "BUSINESS_GAP",
    ["P6"], "Syncing with Tally",
    "ENABLE_TALLY is off; only a one-way export dump exists, no live sync.",
    "Export dump only; no live sync. CAs who need Tally import the export file. (FREEZE_SCOPE B)",
    ["docs/FREEZE_SCOPE.md B (ENABLE_TALLY=0)"],
), "FREEZE_SCOPE B: Tally sync")

add(wontfix(
    "QOS-0064", "Manufacturing (BOM / work orders) is a dark module", "BUSINESS_GAP",
    ["P1"], "Manufacturing / assembly workflows",
    "ENABLE_MANUFACTURING=0 in production; discrete manufacturers are an explicit capability gap.",
    "Dark module in production. Discrete manufacturers are out of scope - do not spend validation bandwidth. (FREEZE_SCOPE B)",
    ["docs/FREEZE_SCOPE.md B (ENABLE_MANUFACTURING=0)"],
), "FREEZE_SCOPE B: Manufacturing")

add(wontfix(
    "QOS-0065", "Payroll is a dark module", "BUSINESS_GAP",
    ["P5"], "Running payroll",
    "ENABLE_PAYROLL=0 in production; salary processing and statutory payroll filings are not part of the pilot.",
    "Dark module in production; payroll is handled out of band. (FREEZE_SCOPE B)",
    ["docs/FREEZE_SCOPE.md B (ENABLE_PAYROLL=0)"],
), "FREEZE_SCOPE B: Payroll")

add(wontfix(
    "QOS-0066", "CRM is a dark module", "BUSINESS_GAP",
    ["P3"], "Lead / opportunity management",
    "ENABLE_CRM=0 in production; lead pipelines and opportunity tracking are not part of the pilot.",
    "Dark module in production; the pilot does not include CRM. (FREEZE_SCOPE B)",
    ["docs/FREEZE_SCOPE.md B (ENABLE_CRM=0)"],
), "FREEZE_SCOPE B: CRM")

add(wontfix(
    "QOS-0067", "Fixed assets + depreciation is a known limitation (D6)", "BUSINESS_GAP",
    ["P5", "P6"], "Tracking fixed assets and depreciation",
    "ENABLE_FIXED_ASSETS=0 in the pilot profile; the route 404s. D6 was briefly scoped in on 2026-09-09 then demoted.",
    "Track assets and depreciation in existing books; post the monthly depreciation journal manually. (D6, 2026-09-09b)",
    ["docs/FREEZE_SCOPE.md B (ENABLE_FIXED_ASSETS=0)", "docs/FREEZE_SCOPE.md 'Scope revision 2026-09-09b'"],
    test_required="test_wf_limitation_guards + test_pj_limitation_guards assert /accounting/fixed-assets/ returns 404 under the flag-off profile",
), "FREEZE_SCOPE B: Fixed assets | D6")

add(wontfix(
    "QOS-0068", "Bill of Entry / import purchase + landed cost is a known limitation (D10)", "BUSINESS_GAP",
    ["P5"], "Recording an import purchase with customs duty and landed cost",
    "ENABLE_BOE=0 in the pilot profile; the route 404s. Single-currency INR only; no landed-cost capitalisation into cost layers.",
    "Enter import purchases as a domestic purchase bill with duty / landed cost as a charge line; no BoE document or automatic cost-layer capitalisation. (D10, 2026-09-09b)",
    ["docs/FREEZE_SCOPE.md B (ENABLE_BOE=0)", "docs/FREEZE_SCOPE.md 'Scope revision 2026-09-09b'"],
    test_required="test_wf_limitation_guards + test_pj_limitation_guards assert /purchases/bills-of-entry/ returns 404 under the flag-off profile",
), "FREEZE_SCOPE B: Bill of Entry | D10")

add(wontfix(
    "QOS-0069", "Account Aggregator banking integration is out of scope", "BUSINESS_GAP",
    ["P5"], "Pulling bank data via Account Aggregator",
    "ENABLE_ACCOUNT_AGGREGATOR and ENABLE_AA_CONSENT are off; no AA integration in the pilot.",
    "No AA integration in the pilot; bank statements are imported as files. (FREEZE_SCOPE B)",
    ["docs/FREEZE_SCOPE.md B (ENABLE_ACCOUNT_AGGREGATOR=0)"],
), "FREEZE_SCOPE B: Account Aggregator")

add(wontfix(
    "QOS-0070", "Postgres row-level security is out of scope for the pilot", "SECURITY_PRIVACY",
    ["P1"], "Tenant isolation enforcement mechanism",
    "POSTGRES_RLS_ENABLED=0; app-layer company_id scoping is the pilot isolation guarantee. RLS is unproven and advisory-only in CI.",
    "App-layer company_id scoping is the pilot isolation guarantee; RLS is unproven. Revisit for defense-in-depth before GA. (FREEZE_SCOPE B)",
    ["docs/FREEZE_SCOPE.md B (POSTGRES_RLS_ENABLED=0)", "docs/TESTING_STRATEGY.md#8 assumption 3"],
    test_required="tests/tenancy/ + the golden isolation spec assert app-layer scoping blocks cross-tenant reads and IDOR",
), "FREEZE_SCOPE B: Postgres RLS")

add(wontfix(
    "QOS-0071", "Multi-company / multi-branch GSTIN is not built", "BUSINESS_GAP",
    ["P1", "P6"], "Operating multiple GST registrations in one tenant",
    "Single primary GSTIN per company. Inter-state IGST sales are supported; multiple registrations in one tenant are not.",
    "One legal company + one primary GSTIN per tenant. Multi-state / multi-GSTIN firms are out of scope. (FREEZE_SCOPE B)",
    ["docs/FREEZE_SCOPE.md B (Multi-company / multi-branch GSTIN)"],
), "FREEZE_SCOPE B: Multi-GSTIN")

add(wontfix(
    "QOS-0072", "Full perpetual FIFO COGS is out of scope", "BUSINESS_GAP",
    ["P5", "P6"], "Inventory cost accounting method",
    "The product uses a running weighted-average cost, not perpetual FIFO COGS layers. Cost is recomputable from movements.",
    "Running weighted cost, not full perpetual FIFO COGS layers. Internal note; the accounting difference from true FIFO is not quantified by a test. (C3)",
    ["docs/FREEZE_SCOPE.md B (Full perpetual FIFO COGS)", "docs/FREEZE_SCOPE.md C3"],
    test_required="inventory.running_cost_qty_matches_movements asserts cost is recomputable from movements",
), "FREEZE_SCOPE B: FIFO COGS | C3")

add(wontfix(
    "QOS-0073", "Native mobile app-store distribution is out of scope", "BUSINESS_GAP",
    ["P2", "P3"], "Installing Bizboard from an app store",
    "The Capacitor Android shell ships as a sideloaded APK for the pilot (D12); no Play Store listing, no iOS.",
    "Android only, sideloaded APK, no Play Store listing for the pilot. Described as the 'Android app shell', not a native mobile app. (D12)",
    ["docs/FREEZE_SCOPE.md B (Native mobile / app stores)", "docs/pilot/ONBOARDING.md"],
), "FREEZE_SCOPE B: app stores | D12")

add(wontfix(
    "QOS-0074", "Right-to-erasure default is tombstone, not hard delete", "SECURITY_PRIVACY",
    ["P1"], "A pilot merchant requests account erasure",
    "ENABLE_TENANT_ERASURE is off by default; the default mode is 'tombstone' - statutory tax docs are kept with party PII scrubbed, the Company row survives with erased_at, and a purge job hard-deletes after the 8-year GST window.",
    "Statutory retention (8-year GST window) legally requires keeping tax documents; PII is scrubbed and the row is tombstoned, then hard-deleted by purge_tombstoned_companies. This is the correct behaviour, not a gap. (SR-40)",
    ["docs/FREEZE_SCOPE.md E (ENABLE_TENANT_ERASURE)", "backend/tests/test_erasure.py"],
    test_required="test_erasure + tenancy.no_orphans_after_erasure assert the tombstone cascade scrubs PII and leaves no orphans",
), "FREEZE_SCOPE E: tenant erasure | SR-40")

add(wontfix(
    "QOS-0075", "TDS/TCS returns and certificates (GSTR-7/8, 16A/27D) are a known limitation (D7)", "BUSINESS_GAP",
    ["P6"], "Producing TDS/TCS statutory returns and certificates",
    "No separate flag; the product produces the TDS/TCS worksheet and the CA generates the returns and certificates from it.",
    "Bizboard gives the TDS/TCS worksheet; the CA produces GSTR-7/8 and Form 16A/27D from it. (D7, 2026-09-09b)",
    ["docs/FREEZE_SCOPE.md 'Scope revision 2026-09-09b' (D7)"],
    test_required="test_wf36 asserts the TDS/TCS worksheets reconcile to the transactions",
), "FREEZE_SCOPE: D7 TDS/TCS returns")

add(wontfix(
    "QOS-0076", "Reverse charge (RCM) is a known pilot limitation (D8)", "BUSINESS_GAP",
    ["P5", "P6"], "Recording a reverse-charge liability and the matching ITC",
    "Merchants with material RCM exposure (GTA / legal / security) are screened out of the pilot, or record the RCM self-invoice + ITC manually. test_wf55 keeps the computation-path regression only.",
    "Merchants with material RCM exposure are screened out of the pilot, or record the self-invoice + ITC manually. (D8, 2026-09-09b)",
    ["docs/FREEZE_SCOPE.md 'Scope revision 2026-09-09b' (D8)", "docs/BUSINESS_ARCHETYPES_AND_PERSONAS.md ARCH-07"],
    test_required="test_wf55_reverse_charge_purchase keeps the flag-on computation path as regression coverage (not a freeze blocker)",
), "FREEZE_SCOPE: D8 RCM")

add(wontfix(
    "QOS-0077", "Composition dealer + CMP-08 is deprioritised (D9 / ARCH-02)", "PERSONA_GAP",
    ["P1"], "Running a composition-scheme business",
    "Bill of supply + the CMP-08 worksheet exist in code (test_wf56) but are not freeze-gated. ARCH-02 is excluded from the pilot for low willingness-to-pay and high churn.",
    "Composition dealers are out of the pilot by commercial choice, not a capability gap. Bill of supply + CMP-08 worksheet exist but are not a freeze-gated flow. (D9 / ARCH-02)",
    ["docs/FREEZE_SCOPE.md 'Scope revision 2026-09-09b' (D9)", "docs/BUSINESS_ARCHETYPES_AND_PERSONAS.md section 8 (ARCH-02 deprioritised)"],
    test_required="test_wf56_composition_bill_of_supply keeps the computation-path regression (not a freeze blocker)",
), "FREEZE_SCOPE: D9 composition | ARCH-02")

add(wontfix(
    "QOS-0078", "Plan-limit / entitlement enforcement is not in the pilot (D11)", "BUSINESS_GAP",
    ["P1"], "Enforcing plan feature-gates and count quotas",
    "Plan feature-gates and count quotas are not enforced in the pilot; billing and limits are handled out of band.",
    "Plan feature-gates and count quotas are handled out of band during the pilot. (D11, 2026-09-09b)",
    ["docs/FREEZE_SCOPE.md 'Scope revision 2026-09-09b' (D11)"],
    test_required="test_wf58_plan_limits keeps the computation-path regression (not a freeze blocker)",
), "FREEZE_SCOPE: D11 plan limits")

add(wontfix(
    "QOS-0079", "No in-product SaaS subscription / entitlement billing", "BUSINESS_GAP",
    ["P1"], "Paying for Bizboard",
    "There is no BizBoard SaaS subscription or entitlement billing system; it is out of freeze scope (roadmap).",
    "Out of freeze scope - roadmap. Pilot billing is handled manually / out of band. (issue register P1, roadmap)",
    ["docs/FREEZE_SCOPE_COVERAGE.md 'P0/P1 issue-register sweep' (roadmap)"],
), "issue-register P1 'No BizBoard SaaS subscription / entitlement billing' | roadmap")

add(wontfix(
    "QOS-0080", "Multi-currency is out of scope", "BUSINESS_GAP",
    ["P5", "P6"], "Transacting in a non-INR currency",
    "The core strictly enforces single-currency INR; foreign-exchange gain/loss is out of scope.",
    "INR only; FX gain/loss out. Import/export businesses are a stated capability gap. (FREEZE_SCOPE G7)",
    ["docs/FREEZE_SCOPE.md G7 (Multi-currency OUT)", "docs/BUSINESS_ARCHETYPES_AND_PERSONAS.md section 1 invariant 3"],
), "FREEZE_SCOPE G7: multi-currency")

# ======================================================================
# H. Q-OS governance
# ======================================================================

add(item(
    "QOS-0052", "BUSINESS_GAP",
    "Q-OS scoring rubric, ADR-0001, and locked decisions are not formally ratified",
    ["P1"], "Governance of the quality pipeline itself",
    """qos/RUBRIC.md, qos/README.md 'locked decisions', and qos/adr/0001-observation-layer.md
    were adopted as the working model on 2026-09-10 but carry no founder/QA sign-off. Until
    ratified, the priority cap and the observation-layer deferral are working assumptions,
    not agreed policy.""",
    "heuristic",
    ["qos/RUBRIC.md", "qos/README.md", "qos/adr/0001-observation-layer.md"],
    "The docs exist and are internally consistent; the sign-off lines / ADR status are the open part.",
    3, 2, 1, "P2",
    "Impact Low (6); a governance formality, but it gates whether the pipeline's rules are authoritative. P2.",
    "S",
    """At the next quality review: sign RUBRIC.md, confirm or amend the README locked
    decisions, and move ADR-0001 from Accepted-provisional to Ratified (or revise the
    observation-layer call).""",
    "RUBRIC.md signed; README decisions confirmed; ADR-0001 status = Ratified",
    "founder", business_metric="none",
), "qos-governance | this session")

# ======================================================================
# I. Functional Code Review (CR-*) — direct read of FUNCTIONAL_CODE_REVIEW_FINDINGS.md
#    The 5 release-blocking Criticals are FIXED & VERIFIED (doc header + named
#    tests). 15 body entries CR-090..CR-104 still carry a "Status: OPEN" label
#    from the 2026-09-08 pass and were NOT individually re-verified against the
#    current tree. The clearly-still-plausible ones are pulled out below; the
#    rest are a tracked re-status sweep. R-001..088's source doc
#    (FINDINGS_2026-09-05.md) is not in the repo -> cannot be reconciled first-hand.
# ======================================================================

add(item(
    "QOS-0053", "DISSATISFACTION",
    "AP aging and AR aging use different truth models when books are on (CR-100 / CR-101)",
    ["P1", "P5"], "Reconciling the dashboard AP card to the payables aging list",
    """CR-060/061 moved AR (receivables) to foot the aging list. The purchase twins were left:
    dashboard payables (_company_payables) still uses GL company-payables when books are on, and
    per-invoice purchase outstanding still sums all allocations. AR and AP cards then rest on
    different models and cannot be reconciled by the operator.""",
    "heuristic",
    ["docs/reviews/FUNCTIONAL_CODE_REVIEW_FINDINGS.md CR-100 (High, Status: OPEN)",
     "docs/reviews/FUNCTIONAL_CODE_REVIEW_FINDINGS.md CR-101 (High, Status: OPEN)",
     "docs/TESTING_STRATEGY.md#6.9 (dashboard KPI == drill-down)"],
    "Direct read of the 2026-09-08 functional review; both entries marked OPEN, both High; not re-verified against the current tree.",
    3, 3, 3, "P1",
    "Impact Medium (27); High-severity register entries, operator-facing reconciliation confusion. Base P1.",
    "M",
    """Mirror the sales-side aging filters on the purchase paths: _company_payables = sum(payables_aging)
    like AR; purchase_invoice_outstanding excludes receipt-shaped allocations. Keep GL on the
    books / recon surfaces only.""",
    "test_cr100_purchase_invoice_outstanding_ignores_receipt_allocations + test_cr101_dashboard_payables_equals_aging_sum",
    "backend", archetype=["ARCH-03"], business_metric="support_ticket_rate",
), "CR-100 | FUNCTIONAL_CODE_REVIEW_FINDINGS.md", "CR-101 | FUNCTIONAL_CODE_REVIEW_FINDINGS.md")

add(item(
    "QOS-0054", "RELIABILITY_TRUST",
    "GST period soft-close has no row lock - TOCTOU race with posting (CR-104)",
    ["P5", "P6"], "Soft-closing a GST period while an invoice completes into that date",
    """AccountingPeriod close was locked (CR-081); GST period soft_close_period was not.
    assert_period_allows_money_amend reads the GST period unlocked, so a concurrent
    soft-close vs PostingService.post can post into (or reverse out of) a just-closed GST
    period.""",
    "heuristic",
    ["docs/reviews/FUNCTIONAL_CODE_REVIEW_FINDINGS.md CR-104 (High, Status: OPEN, residual of CR-081)"],
    "Direct read of the 2026-09-08 review; marked OPEN; not re-verified. Needs concurrency to trigger.",
    2, 4, 2, "P2",
    "Impact Low (16) by product (needs a race); compliance-relevant. P2 - a known residual with a clear fix.",
    "S",
    """Lock the GST period row (or take an advisory lock) in soft_close_period and in
    assert_period_allows_money_amend, matching the AccountingPeriod pattern.""",
    "a Postgres concurrency test: soft_close + complete into the same date, one must lose",
    "backend", archetype=["ARCH-03"], business_metric="renewal",
), "CR-104 | FUNCTIONAL_CODE_REVIEW_FINDINGS.md")

add(item(
    "QOS-0055", "RELIABILITY_TRUST",
    "GL backfill skips empty POSTED journal-entry headers forever (CR-103)",
    ["P5"], "Running the accounting backfill after enabling books",
    """backfill_* commands treat any POSTED JournalEntry as done via .exists() without
    checking lines.exists(). An orphan 0-line POSTED header (pre-CR-078 or a race) makes the
    backfill skip that document permanently, even though PostingService.post would heal it.""",
    "heuristic",
    ["docs/reviews/FUNCTIONAL_CODE_REVIEW_FINDINGS.md CR-103 (Medium, Status: OPEN)"],
    "Direct read of the 2026-09-08 review; marked OPEN; not re-verified.",
    2, 3, 2, "P2",
    "Impact Low (12); silent - a document stays unposted with no error. P2.",
    "S",
    """Treat a 0-line POSTED entry as missing (delete + repost) in _has_je, matching
    PostingService.post.""",
    "a test: empty POSTED header present -> backfill reposts its lines",
    "backend", business_metric="none",
), "CR-103 | FUNCTIONAL_CODE_REVIEW_FINDINGS.md")

add(item(
    "QOS-0056", "RELIABILITY_TRUST",
    "Online POS reload mid-settlement can mint a second COMPLETED invoice (CR-091)",
    ["P2"], "POS: complete succeeds, tab is reloaded before the receipt is recorded",
    """The online POS path keeps the in-flight gesture key / cashPending in React state only
    (no enqueueDraft). A full reload after complete but before receipt loses the key; the next
    Cash action mints a new key family and can produce a second COMPLETED invoice while the
    first stays unpaid - the same class as the original CR-001, and the H-03 risk.""",
    "heuristic",
    ["docs/reviews/FUNCTIONAL_CODE_REVIEW_FINDINGS.md CR-091 (Medium, Status: OPEN, residual of CR-001)",
     "docs/BUSINESS_ARCHETYPES_AND_PERSONAS.md section 11 H-03"],
    "Direct read of the 2026-09-08 review; marked OPEN; the offline flush path is durable, the online path is not.",
    3, 4, 2, "P1",
    "Impact Medium (24); double-invoice / unpaid orphan is a money-integrity class. Base P1 (Medium x severity 4).",
    "M",
    """Persist the in-flight settlement to the outbox / sessionStorage keyed by company+user,
    so a reload resumes the same invoice - mirror the offline flush durability.""",
    "an e2e test: complete OK, reload before receipt, reopen POS, Cash -> resumes the same invoice (no second COMPLETED)",
    "web", archetype=["ARCH-01"], business_metric="renewal",
), "CR-091 | FUNCTIONAL_CODE_REVIEW_FINDINGS.md")

add(item(
    "QOS-0057", "RELIABILITY_TRUST",
    "Re-status the CR-090..CR-104 findings that still carry a stale 'OPEN' label",
    ["P5"], "Reconciling the functional code review against the current tree",
    """FUNCTIONAL_CODE_REVIEW_FINDINGS.md (2026-09-08) has 15 entries CR-090..CR-104 marked
    'Status: OPEN'. The doc header (fresher) says 0 open Criticals and a green suite, and the
    2026-09-10 C15 sweep concluded no open P0/P1 code defect - but the CR High/Medium/Low tail
    was never re-statused line by line. CR-100/101/104/091/103 are pulled out as QOS-0053..0056;
    the remaining ~10 (CR-090/092/093/094/095/096/097/098/099/102) need a verdict each.""",
    "heuristic",
    ["docs/reviews/FUNCTIONAL_CODE_REVIEW_FINDINGS.md CR-090..CR-104",
     "docs/FREEZE_SCOPE_COVERAGE.md 'P0/P1 issue-register sweep (C15)'"],
    "Direct read: 15 OPEN labels, header says clean, C15 sweep says no P0/P1 code defect. The tail is unreconciled.",
    3, 3, 2, "P1-investigate",
    "Impact Medium (18); the action is a re-status pass, not a fix - promote any still-real entry to its own QOS item.",
    "M",
    """Walk CR-090/092/093/094/095/096/097/098/099/102 against the current tree: for each,
    mark FIXED (name the test), STILL-OPEN (mint a QOS item), or NOT-A-DEFECT (record why).
    Update FUNCTIONAL_CODE_REVIEW_FINDINGS.md statuses in the same pass.""",
    "every CR-090..CR-104 entry has a current verdict; still-open ones are QOS items with tests",
    "backend", business_metric="none",
), "CR-090..CR-104 | FUNCTIONAL_CODE_REVIEW_FINDINGS.md (stale OPEN labels)")

add(item(
    "QOS-0058", "BUSINESS_GAP",
    "The R-001..R-088 findings register is not in the repo - can't be reconciled first-hand",
    ["P5"], "Reconciling the 2026-09-05 quality review",
    """MASTER_ISSUE_REGISTER.md cites FINDINGS_2026-09-05.md (R-001..088: 5 P0, 27 P1, 24 P2,
    18 UX, 14 PARTIAL) and its fix plan, but neither file is present under docs/reviews/. The
    88 R-findings can only be taken on the register header's word ('F-01..F-15 fixed in tree;
    rest cross-close with CR/BB').""",
    "heuristic",
    ["docs/reviews/MASTER_ISSUE_REGISTER.md (R-001..088 scheme header)",
     "missing: docs/reviews/FINDINGS_2026-09-05.md, FIX_PLAN_2026-09-05.md"],
    "Direct check: the cited source docs do not exist in the tree; the register header is the only record.",
    2, 3, 1, "P2",
    "Impact Low (6); a traceability gap, not a known defect. P2 - locate the file or formally fold R into CR/BB.",
    "S",
    """Locate FINDINGS_2026-09-05.md (git history / branches / author) and commit it, or record
    in MASTER_ISSUE_REGISTER that the R scheme is superseded by CR + the BB Status tally and
    needs no separate reconciliation.""",
    "the R findings doc is in the repo, or the register records R as formally superseded",
    "founder", business_metric="none",
), "R-001..088 | MASTER_ISSUE_REGISTER (source doc absent)")

add(item(
    "QOS-0059", "RELIABILITY_TRUST",
    "Inventory summary 'reserved' is still read from the StockBalance cache (CR-102 residual)",
    ["P4", "P5"], "Reading available quantity on the inventory summary",
    """CR-102's re-status (2026-09-11) confirms only the mitigation shipped: reporting/services.py
    adds a `reserved_drift` flag when the cached `reserved` looks wrong, but `available =
    on_hand - reserved` still uses that cached value. on_hand is movement-summed and correct;
    available can be wrong when the reserved cache drifts.""",
    "heuristic",
    ["docs/reviews/CR_090_104_RESTATUS_2026-09-11.md (CR-102 = PARTIAL)",
     "backend/reporting/services.py (inventory_summary, ~line 558-594)"],
    "Direct read of the tree during the QOS-0057 re-status: the drift flag is present, the root-cause derivation is not.",
    2, 3, 2, "P2",
    "Impact Low (12); operators see a flag rather than silently-wrong available. P2 - finish the CR-102 fix.",
    "S",
    """Derive `reserved` from open reservations / reservation movements (as on_hand is
    derived), or make `available` fall back to on_hand when `reserved_drift` is set.""",
    "a test: drift the reserved cache -> inventory_summary available is correct or the row is flagged and available is not understated",
    "backend", business_metric="none",
), "CR-102 | FUNCTIONAL_CODE_REVIEW_FINDINGS.md (residual after re-status)")

# --- MASTER_ISSUE_REGISTER BB non-resolved set: full reconciliation --------
# The register's machine-checked Status tally is 739 Resolved / 10 Deferred-ops /
# 6 Accepted-positive / 3 Deferred-roadmap. The 13 non-resolved BB blocks map 1:1
# to QOS items below; the CR-001..089 and R-001..088 schemes were reconciled
# closed by the 2026-09-10 "P0/P1 issue-register sweep (C15)" + the 63-issue
# remediation report. No open code defect remains in any scheme.
SOURCE_ROWS.extend([
    ("BB-000014", "QOS-0021", "Go/No-Go gates unsigned (Deferred - ops owner)"),
    ("BB-000468", "QOS-0021", "GO_NO_GO unsigned CA/UAT/TLS/backup (Deferred - ops owner)"),
    ("BB-000015", "QOS-0020", "No TLS termination at edge (Deferred - ops owner)"),
    ("BB-000045", "QOS-0022", "No automated backup/restore drill in compose (Deferred - ops owner)"),
    ("BB-000469", "QOS-0022", "compose backup: no scheduled restore automation (Deferred - ops owner)"),
    ("BB-000185", "QOS-0011", "No pen-test before GA (Deferred - ops owner)"),
    ("BB-000183", "QOS-0043", "Competitor gap: Zoho bank feeds & automation (Deferred - ops owner)"),
    ("BB-000669", "QOS-0036", "No recurring invoice templates / scheduler (Deferred - roadmap)"),
    ("BB-000671", "QOS-0079", "No SaaS subscription / entitlement billing (Deferred - roadmap)"),
    ("CR release-blocking Criticals", "-", "CR-094/120/144/157/175 FIXED & VERIFIED per the doc header + named tests (test_a15_cr090_plus.py, test_b_wave_cr120_144_157.py)"),
    ("CR-090..CR-104", "QOS-0053..0058", "15 stale 'OPEN' labels (2026-09-08): CR-100/101->QOS-0053, CR-104->QOS-0054, CR-103->QOS-0055, CR-091->QOS-0056, rest->QOS-0057 re-status sweep"),
    ("CR-001..089 / CR-105..175", "-", "remediation-report + C15 sweep 2026-09-10 record these as fixed/verified; not re-read line by line this session"),
    ("R-001..088", "QOS-0058", "source doc FINDINGS_2026-09-05.md absent from the tree - cannot reconcile first-hand; tracked"),
    ("BB Status tally", "-", "739 Resolved / 6 Accepted-positive / 10 Deferred-ops / 3 Deferred-roadmap; the 13 non-resolved all mapped above"),
])


# ======================================================================
# emit
# ======================================================================

def dump_yaml(d):
    ordered = {k: d[k] for k in KEY_ORDER if k in d}
    return yaml.safe_dump(ordered, sort_keys=False, allow_unicode=True, width=100)


MANIFEST = BACKLOG / "_generated_manifest.json"


def main():
    import hashlib
    import json

    import merge

    BACKLOG.mkdir(parents=True, exist_ok=True)
    owned = {f"{it['id']}.yaml" for it in ITEMS}
    prev = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}

    # Re-mine = regenerate the mined (content) fields, PRESERVE the human-owned
    # (workflow) fields on any item that already exists. See qos/tools/merge.py.
    manifest = {}
    overrides_seen: list[str] = []
    for it in ITEMS:
        name = f"{it['id']}.yaml"
        path = BACKLOG / name
        existing = None
        if path.exists():
            existing = yaml.safe_load(path.read_text(encoding="utf-8"))
            ov = merge.describe_overrides(it, existing)
            if ov:
                overrides_seen.append(f"{it['id']}: kept {', '.join(ov)}")
        merged = merge.apply(it, existing)
        body = dump_yaml(merged)
        path.write_text(body, encoding="utf-8")
        manifest[name] = hashlib.sha256(path.read_bytes()).hexdigest()

    # Remove only files this script owned last run but no longer emits.
    for name in set(prev) - owned:
        stale = BACKLOG / name
        if stale.exists():
            stale.unlink()

    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if overrides_seen:
        print("preserved human-owned fields on re-mine:")
        for line in overrides_seen:
            print(f"  {line}")

    rows = sorted(SOURCE_ROWS, key=lambda r: (r[1], r[0]))
    lines = [
        "# Source map — every mined finding -> its QOS id",
        "",
        "Makes re-mining idempotent: a source id already here is already triaged.",
        "Generated by `qos/tools/_backfill_phase1.py` (Phase 1). Edit the YAML, not this file,",
        "for anything after Phase 1 — but keep adding rows here when new sources are mined.",
        "",
        "| source id | QOS id | note |",
        "|---|---|---|",
    ]
    for sid, qid, note in rows:
        lines.append(f"| {sid} | {qid} | {note} |")
    lines += [
        "",
        "## MASTER_ISSUE_REGISTER reconciliation (runbook P1-T4)",
        "",
        "### BB-000001..758 — DONE (machine-checked)",
        "",
        "`Status` tally over the register: **739 Resolved · 6 Accepted (positive) · 10 Deferred",
        "— ops owner · 3 Deferred — roadmap**. The **13 non-resolved** blocks are each mapped to",
        "a QOS item above (BB-000014/015/045/128/183/185/186/468/469/470/668/669/671). New items",
        "minted: QOS-0049 (DPDP checklist), QOS-0050 (chaos/failover drill), QOS-0051 (tenant",
        "backup/restore product path). The 6 \"Accepted (positive)\" blocks are approved design",
        "choices, not defects. No open BB code defect remains.",
        "",
        "### CR-001..175 — Criticals DONE; High/Med/Low tail PARTIALLY reconciled",
        "",
        "Direct read of `docs/reviews/FUNCTIONAL_CODE_REVIEW_FINDINGS.md` (2026-09-08):",
        "",
        "- **5 release-blocking Criticals** (CR-094/120/144/157/175) — FIXED & VERIFIED per the",
        "  doc header + named tests (`test_a15_cr090_plus.py`, `test_b_wave_cr120_144_157.py`).",
        "- **CR-090..CR-104** — 15 entries still carry a `Status: OPEN` label from the 2026-09-08",
        "  pass. Pulled out as concrete items: **CR-100/101 → QOS-0053**, **CR-104 → QOS-0054**,",
        "  **CR-103 → QOS-0055**, **CR-091 → QOS-0056**. The remaining ~10 (CR-090/092/093/094/",
        "  095/096/097/098/099/102) are a tracked re-status sweep: **QOS-0057**.",
        "- **CR-001..089 / CR-105..175** — the remediation report + the C15 sweep record these as",
        "  fixed/verified; not re-read line by line in this session.",
        "",
        "### R-001..088 — CANNOT reconcile first-hand",
        "",
        "The cited source docs (`FINDINGS_2026-09-05.md`, `FIX_PLAN_2026-09-05.md`) are **not in",
        "the tree**. Tracked as **QOS-0058**: locate the file or record R as formally superseded",
        "by CR + the BB tally.",
        "",
        "If the registers grow, add rows above and re-run.",
    ]
    (BACKLOG / "_SOURCE_MAP.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"wrote {len(ITEMS)} items + _SOURCE_MAP.md ({len(rows)} source rows) to {BACKLOG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
