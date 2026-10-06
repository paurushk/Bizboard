# Run pytest against Postgres. SQLite stays the default for a plain `pytest`.
# This is the script for this Windows workstation. scripts/test_postgres.sh is the
# same contract for a POSIX shell; do not require Git Bash here.
$ErrorActionPreference = "Stop"
$DatabaseUrl = $env:DATABASE_URL
$pytestArgs = @()
for ($i = 0; $i -lt $args.Count; $i++) {
    if ($args[$i] -eq "-DatabaseUrl" -and ($i + 1) -lt $args.Count) {
        $DatabaseUrl = $args[$i + 1]
        $i++
        continue
    }
    $pytestArgs += $args[$i]
}
if (-not $DatabaseUrl) {
    $DatabaseUrl = "postgresql://bizboard:bizboard@127.0.0.1:5432/bizboard_test"
}
$env:DATABASE_URL = $DatabaseUrl
$env:PYTEST_KEEP_DATABASE_URL = "1"

$previousErrorAction = $ErrorActionPreference
$ErrorActionPreference = "Continue"
python -c @"
import os, socket, sys, urllib.parse
url = urllib.parse.urlparse(os.environ['DATABASE_URL'])
host = url.hostname or '127.0.0.1'
port = url.port or 5432
sock = socket.socket()
sock.settimeout(2)
try:
    sock.connect((host, port))
except OSError:
    sys.stderr.write('database unreachable\n')
    sys.exit(2)
finally:
    sock.close()
"@
$probeExit = $LASTEXITCODE
$ErrorActionPreference = $previousErrorAction
if ($probeExit -ne 0) {
    exit $probeExit
}

Set-Location (Join-Path $PSScriptRoot "..\backend")
python -m pytest @pytestArgs
exit $LASTEXITCODE
