# Snapshot the dev database before a UX phase. Dev only.
# Usage: .\scripts\ux_phase_snapshot.ps1 -Phase G1
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("G0", "G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9")]
    [string]$Phase
)
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root
if ($env:BB_FULL_DEMO -ne "1") { $env:BB_FULL_DEMO = "1" }

& (Join-Path $PSScriptRoot "compose-env.ps1") dev --profile backup run --rm backup
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$dump = Get-ChildItem -Path (Join-Path $Root "backups") -Filter "bizboard-*" -File |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if (-not $dump) {
    Write-Error "backup profile finished but no bizboard-* dump is in ./backups."
    exit 1
}
$noteDir = Join-Path $Root "backups\ux-phases"
New-Item -ItemType Directory -Force -Path $noteDir | Out-Null
$stamp = Get-Date -Format "yyyyMMddTHHmmss"
$note = Join-Path $noteDir "$Phase-$stamp.txt"
@"
phase=$Phase
dump=$($dump.FullName)
"@ | Set-Content -Path $note -Encoding utf8
Write-Output "Recorded $Phase -> $($dump.Name)"
Write-Output "Restore with: .\scripts\ux_phase_restore.ps1 -Phase $Phase"
