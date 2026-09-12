# Q-OS scoring rubric

The linter (`qos/tools/lint.py`) enforces every rule on this page. Do not score
from feel — use the bands.

## Impact = f(reach, severity, frequency)

Each axis is an integer 1-5.

| Axis | 5 | 4 | 3 | 2 | 1 |
|---|---|---|---|---|---|
| **reach** — of the affected persona population | ~all | majority | ~half | minority | edge |
| **severity** | data loss / money wrong / security breach | blocks the task, no workaround | blocks with a workaround, or clear frustration | mild friction | cosmetic |
| **frequency** | every session | daily | weekly | monthly | rare |

**`impact_band`** (computed, check L5):

- **High** — `reach * severity * frequency >= 45`, **or** `severity == 5`
- **Medium** — product in `18 .. 44`
- **Low** — product `< 18`

## Priority

Map `impact_band` to a base priority, then **cap by evidence strength**:

| impact_band | base priority |
|---|---|
| High | P0 |
| Medium | P1 |
| Low | P2 |

Judgement may lower the priority (dependency ordering, strategic sequencing) but
never raise it above the cap below.

### Evidence-strength -> priority cap (check L3)

| `evidence.strength` | meaning | max priority allowed |
|---|---|---|
| `measured` | real pilot telemetry | P0 |
| `simulated` | Q-OS persona agent, n >= 5 runs (check L4) | P0 |
| `single-run` | one agent pass or one manual walkthrough | `P0-confirm` (with a scheduled confirmation run) |
| `heuristic` | static analysis, expert read of the code/tests | **P1** (never P0) |
| `hypothesis` | inferred from a gap, not observed | **P1-investigate** — an investigation priority, never a fix priority |

**Exemption:** a `SECURITY_PRIVACY` item with `severity == 5` may carry any
priority regardless of evidence strength (assume-true until disproven).

`P1-investigate` and `P0-confirm` are real priority values — they mean "the next
action is to get better evidence", not "fix now".

## Effort

| band | meaning |
|---|---|
| S | < 1 day |
| M | < 1 week |
| L | < 1 month |
| XL | epic — split it |

## Frontier value (how "do next" is ordered)

```
value = priority_weight * impact_weight * evidence_confidence / effort_cost

priority_weight : P0 100 | P0-confirm 80 | P1 40 | P1-investigate 20 | P2 10 | P3 3
impact_weight   : High 3 | Medium 2 | Low 1
evidence_conf   : measured 1.0 | simulated 0.9 | single-run 0.7 | heuristic 0.5 | hypothesis 0.3
effort_cost     : S 1 | M 3 | L 8 | XL 20
```

Ordering also respects `depends_on` — an item never ranks above an unresolved
blocker.

## Worked examples

1. **FE role-hiding untested** — reach 4 (all non-owner users), severity 3
   (frustration, no data risk), frequency 4 (daily). Product 48 -> **High**.
   Evidence `heuristic` -> cap **P1**. `effort` M. `value = 40*3*0.5/3 = 20.0`.

2. **No CA has filed from worksheets (H-05)** — reach 5, severity 4, frequency 3.
   Product 60 -> **High**. Evidence `hypothesis` -> **P1-investigate**.
   The fix is not code; the next action is Stage-3 pilot fieldwork.

3. **Missing FEFO guard-band parametrisation** — reach 2 (pharma archetype only),
   severity 4 (expired stock could ship), frequency 2. Product 16 -> **Low** by
   product but `severity 4` keeps it Medium? No — the `severity == 5` rule is the
   only override; severity 4 with product 16 is **Low**. Evidence `heuristic` ->
   **P1** base is P2 for Low; stays **P2**. `effort` S.

---

## Ratification status

**Adopted 2026-09-10** as the working model — enforced by `qos/tools/lint.py`
(checks L3, L4, L5) and used by `qos/tools/frontier.py`. Formal founder + QA
sign-off is an open item tracked as **QOS-0052** and is a standing agenda item at
the next quality review. Recalibrate quarterly against 10 closed items (see
`qos/README.md` cadence table).

| Sign-off | Name | Date |
|---|---|---|
| Scoring model (founder) | _pending — QOS-0052_ | |
| Linter enforcement (QA) | _pending — QOS-0052_ | |
