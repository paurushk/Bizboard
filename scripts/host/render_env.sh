#!/usr/bin/env bash
# WP-4 (BB-081): build the deploy .env from a secret store at deploy time, so secrets never sit in
# the repository and the file on the host can be re-rendered after a rotation.
#
#   scripts/host/render_env.sh <source> <out-file> [source args]
#
# Sources (provider-neutral; pick the one your host offers):
#   file <path>              copy KEY=VALUE lines from a file kept outside the repo (first staging)
#   aws-ssm <path-prefix>    AWS SSM Parameter Store, every SecureString under the prefix
#   azure-kv <vault-name>    Azure Key Vault, every enabled secret (name dashes -> underscores)
#   gcp-sm <project>         Google Secret Manager, latest version of every secret labelled bizboard=1
#   cmd "<command>"          any command that prints KEY=VALUE lines (Doppler, 1Password CLI, Vault, ...)
#
# The output starts from .env.production.example's keys: a key the store does not provide keeps the
# example value only when it is not a placeholder; otherwise the script stops and lists it, so a
# deploy never boots with CHANGE_ME values. The file is written with mode 600.
set -euo pipefail
cd "$(dirname "$0")/../.."
SRC="${1:?usage: render_env.sh <file|aws-ssm|azure-kv|gcp-sm|cmd> <out-file> [args]}"
OUT="${2:?out file}"
ARG="${3:-}"
TEMPLATE="${TEMPLATE:-.env.production.example}"

tmp="$(mktemp)"; trap 'rm -f "$tmp" "$tmp.kv"' EXIT
case "$SRC" in
  file) [[ -f "$ARG" ]] || { echo "no file $ARG" >&2; exit 1; }; grep -E '^[A-Za-z_][A-Za-z0-9_]*=' "$ARG" > "$tmp.kv" ;;
  aws-ssm)
    aws ssm get-parameters-by-path --path "${ARG:?prefix}" --recursive --with-decryption \
      --query 'Parameters[*].[Name,Value]' --output text \
      | awk -F'\t' '{n=$1; sub(".*/","",n); print n"="$2}' > "$tmp.kv" ;;
  azure-kv)
    for name in $(az keyvault secret list --vault-name "${ARG:?vault}" --query '[?attributes.enabled].name' -o tsv); do
      printf '%s=%s\n' "${name//-/_}" "$(az keyvault secret show --vault-name "$ARG" --name "$name" --query value -o tsv)"
    done > "$tmp.kv" ;;
  gcp-sm)
    for name in $(gcloud secrets list --project "${ARG:?project}" --filter='labels.bizboard=1' --format='value(name)'); do
      printf '%s=%s\n' "$name" "$(gcloud secrets versions access latest --secret "$name" --project "$ARG")"
    done > "$tmp.kv" ;;
  cmd) bash -c "${ARG:?command}" | grep -E '^[A-Za-z_][A-Za-z0-9_]*=' > "$tmp.kv" ;;
  *) echo "unknown source $SRC" >&2; exit 2 ;;
esac

"${PYTHON:-python3}" - "$TEMPLATE" "$tmp.kv" "$tmp" <<'PY'
import re, sys
template, store, out = sys.argv[1:4]
PLACEHOLDER = re.compile(r"(CHANGE_?ME|change-me|REPLACE|your[-_]|example\.com|<.*>|xxx)", re.I)
vals = {}
for line in open(store, encoding="utf-8"):
    k, _, v = line.rstrip("\n").partition("=")
    vals[k.strip()] = v
lines, missing, seen = [], [], set()
for line in open(template, encoding="utf-8"):
    m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", line.rstrip("\n"))
    if not m:
        continue
    k, default = m.group(1), m.group(2)
    seen.add(k)
    if k in vals:
        lines.append(f"{k}={vals[k]}")
    elif default and PLACEHOLDER.search(default):
        missing.append(k)
    else:
        lines.append(f"{k}={default}")
lines += [f"{k}={v}" for k, v in vals.items() if k not in seen]
if missing:
    sys.exit("missing from the secret store (template value is a placeholder): " + ", ".join(missing))
open(out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
print(f"{len(lines)} keys rendered")
PY
install -m 600 "$tmp" "$OUT"
echo "wrote $OUT (mode 600). Run scripts/host/preflight.py --env-file $OUT next."
