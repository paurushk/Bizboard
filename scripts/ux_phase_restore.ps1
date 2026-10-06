# Restore the newest snapshot labelled for a UX phase. Overwrites the dev database.
# Usage: .\scripts\ux_phase_restore.ps1 -Phase G1
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("G0", "G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9")]
    [string]$Phase
)
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root
$noteDir = Join-Path $Root "backups\ux-phases"
$note = Get-ChildItem -Path $noteDir -Filter "$Phase-*.txt" -File -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if (-not $note) {
    Write-Error "No snapshot label for $Phase in backups/ux-phases. Run ux_phase_snapshot.ps1 first."
    exit 1
}
$dumpLine = (Get-Content $note.FullName | Where-Object { $_ -like "dump=*" } | Select-Object -First 1)
$dump = $dumpLine.Substring(5)
if (-not (Test-Path $dump)) {
    Write-Error "Snapshot file missing: $dump"
    exit 1
}
$env:RESTORE_FILE = $dump
if ($env:BB_FULL_DEMO -ne "1") { $env:BB_FULL_DEMO = "1" }
& (Join-Path $PSScriptRoot "compose-env.ps1") dev --profile restore run --rm restore
exit $LASTEXITCODE
