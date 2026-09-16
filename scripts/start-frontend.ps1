$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath (Join-Path $ProjectRoot "frontend")

npm run dev

