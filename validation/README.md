# Graph 1 — Flow catalog

Generated inventory of every router path and in-page money action, with a
coverage label. Philosophy lives in
[`docs/HOLISTIC_VALIDATION_REVIEW.md`](../docs/HOLISTIC_VALIDATION_REVIEW.md).
Build order lives in
[`docs/HOLISTIC_VALIDATION_IMPLEMENTATION_PLAN.md`](../docs/HOLISTIC_VALIDATION_IMPLEMENTATION_PLAN.md).

**Do not hand-edit** `docs/FLOW_CATALOG.md` or `validation/catalog/routes.yaml`.
Correct a label in `validation/overrides.yaml` and re-run the builder.

## Locked decisions (working defaults, 2026-09-13)

Flag to the founder before Phase 1 code merges to `main`, not before it's written.

| # | Decision | Locked default | Who signs | Backstop |
|---|---|---|---|---|
| A1 | Catalogs live here | `validation/` at repo root | founder (flag before merge) | Plain Python + generated markdown |
| A2 | Route extraction | Python state machine over `App.tsx` JSX | web lead owns breakage | Fail loud (parse error / count floor) |
| A3 | CI gate blocking? | Advisory until 2 consecutive green CI weeks, then web lead flips | web lead | Same pattern as `load-harness` |
| A4 | Projection identities | (Phase 3) new `@invariant`s, existing strict sweep | backend lead | No new opt-out |
| A5 | Event matrix owner | backend lead writers / web lead UI cells | founder only for a **new event class** | |
| A6 | Lifecycle goldens | New files, same `e2e-golden` job initially | web lead | Split only if runtime +>~5 min |

## Layout

```
validation/
  README.md
  overrides.yaml              human corrections (D5)
  schema/flow_item.schema.json
  schema/action_item.schema.json
  catalog/
    actions.yaml              hand-seeded in-page money actions (P1-T3)
    freeze_route_map.yaml     A-row / OUT / LIM prefixes + P1-T5 persona join
    events.yaml               Graph 2 verbs (P2-T1)
    routes.yaml               GENERATED
    flow_items.yaml           GENERATED
    route_count.json          GENERATED count floor
    event_matrix.yaml         GENERATED
  tools/
    extract_routes.py
    extract_actions.py
    build_flow_catalog.py
    build_event_matrix.py
    check_money_verbs.py      advisory grep (D8)
```

## Commands

```
pip install -r scripts/requirements-tools.txt
python validation/tools/extract_routes.py --selftest
python validation/tools/extract_actions.py --selftest
python validation/tools/build_flow_catalog.py --selftest
python validation/tools/build_event_matrix.py --selftest
python validation/tools/build_flow_catalog.py
python validation/tools/build_event_matrix.py
python validation/tools/extract_routes.py --count
```

CI: `flow-catalog` job is **advisory** (`continue-on-error: true`) until two
green weeks, then the web lead removes that flag. `git diff --exit-code`
on `docs/FLOW_CATALOG.md` and `docs/EVENT_MATRIX.md` is the drift contract (D18).

## Convention — new in-page money action

Add a row to `catalog/actions.yaml` in the same PR. Detecting a *new* button
is honor-system; `check_money_verbs.py` is an advisory grep of `.complete(`,
`.allocate(`, `/reverse/`, etc. in a frontend diff, not a hard gate (D8).

## Coverage labels

`JOURNEY` / `API-ONLY` / `SMOKE` / `FLAG-OFF` / `UNIT` / `GAP` / `OUT` / `LIM` / `UNMAPPED`

- `UNMAPPED` — no FREEZE_SCOPE.md A-row. Expected on day one; blocks only after Phase 6 flips the gate.
- `LIM` — reachable but not freeze-journeyed (e.g. `/sales/recurring`, B7).
- `OUT` — dark / NOT SUPPORTED. BoE is `OUT + known-defect-not-gated` (B6, needs founder override).
