# verify_fixed — 2026-10-26 (QOS-0019 mutation lane)

The CI mutation lane was a silent no-op (mutmut 3 rejected the mutmut-2 flags; `|| true` hid it). Fixed:
targets in `backend/setup.cfg [mutmut]`, `scripts/mutation_audit.sh` fails on a real error, and
`scripts/ci_gates/mutation_score.py` gates each module against `scripts/ci_gates/mutation_baseline.json`.
Survivors triaged with new tests (TCS and TDS worksheets, stock valuation paths) and a wider test selection.

| Module | First real run | Now | Target 80% |
|---|---|---|---|
| core.services.place_of_supply | 98.5% | 99.2% | met |
| accounting.services | 62.8% | 82.0% | met |
| inventory.services | 44.4% | 90.2% | met |
| reporting.tds_worksheets | 39.9% | 95.8% | met |

Runs: mutmut 3.8 in python:3.13-slim (2026-10-24..26); run 3 covered inventory and tds_worksheets only.
