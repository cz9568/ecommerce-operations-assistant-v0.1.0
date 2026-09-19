$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

$BackendPort = 8011
$env:APP_PORT = [string]$BackendPort

& ".\.venv\Scripts\uvicorn.exe" backend.app.main:app `
    --reload `
    --host 127.0.0.1 `
    --port $BackendPort
