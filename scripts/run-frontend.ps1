param(
    [string] $Script = "dev",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $NpmArgs
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$frontendDir = Join-Path $repoRoot "frontend"
$packageJson = Join-Path $frontendDir "package.json"
$nodeModules = Join-Path $frontendDir "node_modules"

if (-not (Test-Path $packageJson)) {
    Write-Host "frontend/package.json was not found." -ForegroundColor Red
    exit 1
}

$nodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
if ($null -eq $nodeCommand) {
    Write-Host "Node.js was not found in PATH." -ForegroundColor Red
    Write-Host "Install Node.js, then run again: .\scripts\run-frontend.cmd"
    exit 1
}

$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
if ($null -eq $npmCommand) {
    Write-Host "npm.cmd was not found in PATH." -ForegroundColor Red
    Write-Host "Install Node.js with npm, then run again: .\scripts\run-frontend.cmd"
    exit 1
}

Write-Host "Using Node:"
& node.exe --version
Write-Host "Using npm:"
& npm.cmd --version

Push-Location $frontendDir
try {
    if (-not (Test-Path $nodeModules)) {
        Write-Host "frontend/node_modules was not found. Running npm install..."
        & npm.cmd install
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    }

    Write-Host "Running npm script: $Script"
    & npm.cmd run $Script -- @NpmArgs
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
