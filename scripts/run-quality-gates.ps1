param(
    [switch]$SkipDependencyAudit
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ReportsPath = Join-Path $ProjectRoot "reports"
Set-Location -LiteralPath $ProjectRoot
New-Item -ItemType Directory -Force -Path $ReportsPath | Out-Null

& ".\.venv\Scripts\ruff.exe" check backend
if ($LASTEXITCODE -ne 0) { throw "Ruff check failed." }
& ".\.venv\Scripts\python.exe" -m pytest --junitxml="reports/pytest.xml"
if ($LASTEXITCODE -ne 0) { throw "Backend tests failed." }
& ".\.venv\Scripts\python.exe" -m backend.scripts.security_scan
if ($LASTEXITCODE -ne 0) { throw "Secret-pattern scan failed." }

Push-Location -LiteralPath "frontend"
try {
    npm ci
    if ($LASTEXITCODE -ne 0) { throw "Frontend dependency installation failed." }
    npm run type-check
    if ($LASTEXITCODE -ne 0) { throw "Frontend type check failed." }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
    if (-not $SkipDependencyAudit) {
        npm audit --omit=dev --audit-level=high
        if ($LASTEXITCODE -ne 0) { throw "Frontend production dependency audit failed." }
    }
}
finally {
    Pop-Location
}

if (-not $SkipDependencyAudit) {
    uv export --frozen --no-dev --format requirements-txt --output-file "reports/runtime-requirements.txt"
    if ($LASTEXITCODE -ne 0) { throw "Runtime dependency export failed." }
    uvx pip-audit -r "reports/runtime-requirements.txt" --format json --output "reports/pip-audit.json"
    if ($LASTEXITCODE -ne 0) { throw "Backend dependency audit failed." }
    uvx bandit -r backend/app -lll -f json -o "reports/bandit.json"
    if ($LASTEXITCODE -ne 0) { throw "High-severity static security issue found." }
}

Write-Host "All quality gates passed. Evidence is available in reports/."
