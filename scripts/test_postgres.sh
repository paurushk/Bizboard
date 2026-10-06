#!/bin/sh
# Same contract as scripts/test_postgres.ps1 for a POSIX shell. The Windows
# workstation runs the PowerShell script; this file is for Linux CI and for
# a developer who already has a POSIX shell. Do not require Git Bash.
set -eu
DATABASE_URL="${DATABASE_URL:-postgresql://bizboard:bizboard@127.0.0.1:5432/bizboard_test}"
export DATABASE_URL
export PYTEST_KEEP_DATABASE_URL=1
python - <<'PY'
import os, socket, sys, urllib.parse
url = urllib.parse.urlparse(os.environ["DATABASE_URL"])
host = url.hostname or "127.0.0.1"
port = url.port or 5432
sock = socket.socket()
sock.settimeout(2)
try:
    sock.connect((host, port))
except OSError:
    sys.stderr.write("database unreachable\n")
    sys.exit(2)
finally:
    sock.close()
PY
cd "$(dirname "$0")/../backend"
exec python -m pytest "$@"
