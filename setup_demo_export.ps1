# PMS Dashboard - Standalone Demo Generator
# Copies and configures the complete frontend into D:\Projects\PMS_Dashboard_demo

$TargetDir = "D:\Projects\PMS_Dashboard_demo"
$SourceDir = "$PSScriptRoot\Frontend"

Write-Host "======================================================" -ForegroundColor Cyan
Write-Host "   PMS Dashboard - Exporting Demo Application         " -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host "Source : $SourceDir"
Write-Host "Target : $TargetDir"
Write-Host ""

# Create target directory if it doesn't exist
if (!(Test-Path $TargetDir)) {
    Write-Host "Creating target directory: $TargetDir..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null
}

# Directories and files to copy
$ItemsToCopy = @(
    "src",
    "public",
    "index.html",
    "package.json",
    "vite.config.ts",
    "tsconfig.json",
    "tsconfig.app.json",
    "tsconfig.node.json",
    "eslint.config.js"
)

foreach ($item in $ItemsToCopy) {
    $srcPath = Join-Path $SourceDir $item
    $dstPath = Join-Path $TargetDir $item
    if (Test-Path $srcPath) {
        Write-Host "Copying $item..." -ForegroundColor Green
        Copy-Item -Path $srcPath -Destination $dstPath -Recurse -Force
    }
}

# Create .env.local in target with Demo Mode enabled
$EnvContent = @"
VITE_API_BASE_URL=
VITE_DEMO_MODE=true
VITE_REALTIME_ENABLED=false
VITE_REPORT_CENTER_ENABLED=true
"@

Set-Content -Path (Join-Path $TargetDir ".env.local") -Value $EnvContent
Write-Host "Configured .env.local with VITE_DEMO_MODE=true" -ForegroundColor Green

Write-Host ""
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host "   Demo Export Complete!                              " -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host "To run the demo application:"
Write-Host "  cd D:\Projects\PMS_Dashboard_demo" -ForegroundColor Yellow
Write-Host "  npm install" -ForegroundColor Yellow
Write-Host "  npm run dev" -ForegroundColor Yellow
Write-Host "======================================================" -ForegroundColor Cyan
