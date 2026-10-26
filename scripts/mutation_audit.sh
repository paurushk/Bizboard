#!/usr/bin/env bash
# Mutation audit of the crown-jewel money / tax / stock modules (stabilization WP-5).
#
# mutmut 3 takes its targets, test selection and copied files from backend/setup.cfg [mutmut];
# it has no command-line flags for them (the old --paths-to-mutate/--runner flags made every run
# fail silently). mutmut has no native-Windows support: run on Linux, in WSL, or in CI.
#
# Each surviving mutant is a missing assertion: add it to core/invariants/ or tests/gst/.
# The per-module score must not drop below scripts/ci_gates/mutation_baseline.json.
#
# Usage:  scripts/mutation_audit.sh            # run + gate against the baseline
#         scripts/mutation_audit.sh results    # show survivors from the last run
#         scripts/mutation_audit.sh baseline   # run + record a new baseline
set -euo pipefail
cd "$(dirname "$0")/../backend"

if [ "${1:-run}" = "results" ]; then
  python -m mutmut results
  exit 0
fi

python -m pip install --quiet "mutmut>=3.2"
# Tests reach repo files through parents[2] of backend/mutants/tests/<file>, i.e. backend/: link the
# repo-level folders in for the run (removed again on exit).
linked=()
for d in docs .github scripts web; do
  if [ ! -e "$d" ]; then ln -s "../$d" "$d" && linked+=("$d"); fi
done
trap 'for d in "${linked[@]}"; do rm -f "$d"; done' EXIT
python -m mutmut run --max-children "${MUTMUT_CHILDREN:-4}"
python -m mutmut results --all true > mutation_results.txt

echo
echo "Survivors (each = a missing assertion; add it, don't ignore it):"
grep -E ": (survived|no tests)$" mutation_results.txt || true
echo
if [ "${1:-run}" = "baseline" ]; then
  python ../scripts/ci_gates/mutation_score.py mutation_results.txt --update
else
  python ../scripts/ci_gates/mutation_score.py mutation_results.txt
fi
