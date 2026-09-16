param(
    [string]$Username = "admin",
    [string]$DisplayName = "System Administrator"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

& ".\.venv\Scripts\python.exe" -m backend.scripts.create_admin `
    --username $Username `
    --display-name $DisplayName
