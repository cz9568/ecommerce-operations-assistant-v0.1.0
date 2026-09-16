$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

& ".\.venv\Scripts\uvicorn.exe" backend.app.main:app `
    --reload `
    --host 127.0.0.1 `
    --port 8000

