param(
    [switch]$SkipFrontend
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

if (-not (Test-Path -LiteralPath ".env")) {
    throw "Missing .env. Copy .env.example and fill in local settings."
}

Write-Host "[1/4] Syncing Python dependencies"
uv sync

if (-not $SkipFrontend) {
    Write-Host "[2/4] Installing frontend dependencies"
    Push-Location -LiteralPath "frontend"
    try {
        npm install
    }
    finally {
        Pop-Location
    }
}
else {
    Write-Host "[2/4] Frontend dependency installation skipped"
}

Write-Host "[3/4] Applying database migrations"
& ".\.venv\Scripts\alembic.exe" upgrade head

Write-Host "[4/4] Verifying environment"
& ".\.venv\Scripts\python.exe" -m backend.scripts.verify_environment

Write-Host "Bootstrap complete. Run scripts/create-admin.ps1 to create the first admin."
