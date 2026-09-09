#!/usr/bin/env bash
# One-shot mutation audit of the crown-jewel modules (Phase 2, FG-2h).
#
# NOTE: mutmut has no native-Windows support (needs WSL / Linux). Run this on a
# Linux box, in WSL, or as a manual CI job. It is a one-shot sanity check, not a
# gate — making mutation testing continuous is Phase 5.
#
# NOT a CI gate — a manual sanity check that the invariant / matrix suite
# actually constrains the code an LLM edits most. Run it once when the Phase 2
# invariants + matrices are green; read the survivors; each surviving mutant is a
# missing assertion — add it to core/invariants/ or tests/gst/ ; then stop.
# Making mutation testing a continuous CI gate is Phase 5.
#
# Usage:  scripts/mutation_audit.sh          # run
#         scripts/mutation_audit.sh results  # show survivors from the last run
set -euo pipefail
cd "$(dirname "$0")/../backend"

TARGETS=(
  "accounting/services.py"
  "core/services/place_of_supply.py"
  "core/services/billing.py"          # is_intra_state / extract_state_code
  "reporting/tds_worksheets.py"
  "inventory/services.py"
)

# Fast subset that exercises the targets — keep this tight so a run finishes.
RUNNER="python -m pytest tests/gst/ tests/workflows/test_wf01_sale_intrastate.py \
  tests/workflows/test_wf04_purchase.py tests/test_invariants_smoke.py \
  tests/test_money_contract.py -q -p no:randomly"

if [ "${1:-run}" = "results" ]; then
  python -m mutmut results
  exit 0
fi

python -m pip install --quiet "mutmut>=3.2"
python -m mutmut run \
  --paths-to-mutate "$(IFS=,; echo "${TARGETS[*]}")" \
  --runner "$RUNNER" \
  --no-progress || true

echo
echo "Survivors (each = a missing assertion; add it, don't ignore it):"
python -m mutmut results
