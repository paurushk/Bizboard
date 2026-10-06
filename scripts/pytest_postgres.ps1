# Run the Postgres-marked backend tests. SQLite stays the default for plain pytest.
# Requires DATABASE_URL pointing at a migrated Postgres database.
$ErrorActionPreference = "Stop"
if (-not $env:DATABASE_URL) {
    Write-Error "DATABASE_URL is not set. Example: postgresql://bizboard:bizboard@localhost:5432/bizboard"
}
# settings_test drops DATABASE_URL unless this is set, and the postgres marker
# would then skip on SQLite.
$env:PYTEST_KEEP_DATABASE_URL = "1"
Set-Location (Join-Path $PSScriptRoot "..\backend")
python -m pytest -m postgres @args
