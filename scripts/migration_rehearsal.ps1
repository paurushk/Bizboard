# Rehearse migrating an N-1 database. The database name must contain "rehearsal".
# Seed with the previous tree (latest tag, or commit 5deafb2), then migrate with
# this tree. Do not point current models at an N-1 schema.
$ErrorActionPreference = "Stop"
$DatabaseUrl = $env:DATABASE_URL
if (-not $DatabaseUrl) {
    Write-Error "DATABASE_URL is not set. Use a database whose name contains 'rehearsal'."
}
if ($DatabaseUrl -notmatch "rehearsal") {
    Write-Error "Refusing to run: database name must contain 'rehearsal'."
}
Write-Output "migration rehearsal: seed from a worktree at the latest tag or 5deafb2, then migrate this tree."
Write-Output "This script does not seed current models onto an older schema."
exit 2
