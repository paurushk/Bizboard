# Run docker compose against the DEV or STAGING overlay.
# Usage:
#   .\scripts\compose-env.ps1 dev up -d
#   .\scripts\compose-env.ps1 staging --profile migrate run --rm migrate
#   .\scripts\compose-env.ps1 staging up -d
#   .\scripts\compose-env.ps1 staging exec api python manage.py seed_staging
param(
    [Parameter(Position = 0, Mandatory = $true)]
    [ValidateSet("dev", "staging")]
    [string]$Environment
)
$ComposeArgs = $args
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

if ($Environment -eq "dev") {
    $envFile = if (Test-Path ".env.dev") { ".env.dev" } else { ".env" }
    $files = @("--env-file", $envFile, "-f", "docker-compose.yml", "-f", "docker-compose.dev.yml")
} else {
    if (-not (Test-Path ".env.staging")) {
        Write-Error "Missing .env.staging - copy .env.staging.example first."
        exit 1
    }
    $files = @("--env-file", ".env.staging", "-f", "docker-compose.yml", "-f", "docker-compose.staging.yml")
}

& docker compose @files @ComposeArgs
exit $LASTEXITCODE
