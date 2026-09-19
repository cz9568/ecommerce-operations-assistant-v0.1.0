param(
    [string]$Version = "0.1.0",
    [switch]$SkipVerification
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ReleaseRoot = Join-Path $ProjectRoot "release"
$ArchivePath = Join-Path $ReleaseRoot "ecommerce-operations-assistant-v$Version.zip"
$TempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$StagePath = Join-Path $TempRoot ("ecommerce-operations-assistant-" + [guid]::NewGuid().ToString("N"))
$PackagePath = Join-Path $StagePath "ecommerce-operations-assistant"

if (-not $SkipVerification) {
    & (Join-Path $PSScriptRoot "run-quality-gates.ps1")
}

New-Item -ItemType Directory -Force -Path $PackagePath | Out-Null
$Files = @(
    ".env.example", ".dockerignore", ".github", "Dockerfile", "docker-compose.yml", "VERSION",
    "README.md", "CHANGELOG.md", "alembic.ini", "pyproject.toml", "uv.lock",
    "backend", "scripts", "docs",
    "电商运营助手.md", "电商运营助手-需求分析与任务拆解.md",
    "技术方案与开发约定.md", "项目进度.md"
)
foreach ($Item in $Files) {
    $Source = Join-Path $ProjectRoot $Item
    if (Test-Path -LiteralPath $Source) {
        Copy-Item -LiteralPath $Source -Destination $PackagePath -Recurse -Force
    }
}

$FrontendPackage = Join-Path $PackagePath "frontend"
New-Item -ItemType Directory -Force -Path $FrontendPackage | Out-Null
foreach ($FrontendItem in @(
    "index.html", "package.json", "package-lock.json", "tsconfig.json", "tsconfig.app.json",
    "tsconfig.node.json", "vite.config.ts", "Dockerfile", "nginx.conf", "src", "dist"
)) {
    $FrontendSource = Join-Path $ProjectRoot "frontend\$FrontendItem"
    if (Test-Path -LiteralPath $FrontendSource) {
        Copy-Item -LiteralPath $FrontendSource -Destination $FrontendPackage -Recurse -Force
    }
}

$PackageStorage = Join-Path $PackagePath "storage"
New-Item -ItemType Directory -Force -Path $PackageStorage | Out-Null
Copy-Item -LiteralPath (Join-Path $ProjectRoot "storage\.gitkeep") -Destination $PackageStorage

$ResolvedStage = [System.IO.Path]::GetFullPath($StagePath)
$ResolvedPackage = [System.IO.Path]::GetFullPath($PackagePath)
if (-not $ResolvedStage.StartsWith($TempRoot, [System.StringComparison]::OrdinalIgnoreCase) -or
    -not $ResolvedPackage.StartsWith($ResolvedStage, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to clean a staging directory outside the system temp directory."
}
Get-ChildItem -LiteralPath $PackagePath -Directory -Recurse -Force |
    Where-Object { $_.Name -in @("node_modules", "__pycache__", ".pytest_cache", ".ruff_cache") } |
    Sort-Object FullName -Descending |
    ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force }

New-Item -ItemType Directory -Force -Path $ReleaseRoot | Out-Null
Compress-Archive -Path $PackagePath -DestinationPath $ArchivePath -CompressionLevel Optimal -Force
$Hash = (Get-FileHash -LiteralPath $ArchivePath -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content -LiteralPath "$ArchivePath.sha256" -Value "$Hash  $(Split-Path -Leaf $ArchivePath)" -Encoding ascii

Remove-Item -LiteralPath $ResolvedStage -Recurse -Force
Write-Host "Release package: $ArchivePath"
Write-Host "SHA-256: $Hash"
