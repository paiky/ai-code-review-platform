param(
    [string] $Script = "dev",
    [string] $ApiProxyTarget = "",
    [string] $HostAddress = "",
    [Nullable[int]] $Port = $null,
    [switch] $StrictPort,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $NpmArgs
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$frontendDir = Join-Path $repoRoot "frontend"
$packageJson = Join-Path $frontendDir "package.json"
$nodeModules = Join-Path $frontendDir "node_modules"
$localGitLabEnv = Join-Path $repoRoot ".local\gitlab.env"

function Import-DotEnvIfPresent {
    param([string] $Path)

    if (-not (Test-Path $Path)) {
        return
    }

    Write-Host "Loading local env: $Path"
    Get-Content -Path $Path -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if ([string]::IsNullOrWhiteSpace($line) -or $line.StartsWith("#")) {
            return
        }

        $separatorIndex = $line.IndexOf("=")
        if ($separatorIndex -le 0) {
            return
        }

        $key = $line.Substring(0, $separatorIndex).Trim()
        $value = $line.Substring($separatorIndex + 1).Trim()
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        [Environment]::SetEnvironmentVariable($key, $value, "Process")
    }
}

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
Import-DotEnvIfPresent $localGitLabEnv

Push-Location $frontendDir
try {
    if (-not [string]::IsNullOrWhiteSpace($ApiProxyTarget)) {
        $env:VITE_API_PROXY_TARGET = $ApiProxyTarget
    }
    elseif ([string]::IsNullOrWhiteSpace($env:VITE_API_PROXY_TARGET)) {
        $env:VITE_API_PROXY_TARGET = "http://localhost:8090"
    }
    Write-Host "Using API proxy target: $env:VITE_API_PROXY_TARGET"

    if (-not (Test-Path $nodeModules)) {
        Write-Host "frontend/node_modules was not found. Running npm install..."
        & npm.cmd install
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    }

    $effectiveNpmArgs = @($NpmArgs)
    if (-not [string]::IsNullOrWhiteSpace($HostAddress)) {
        $effectiveNpmArgs += @("--host", $HostAddress)
    }
    if ($null -ne $Port) {
        $effectiveNpmArgs += @("--port", [string] $Port)
    }
    if ($StrictPort) {
        $effectiveNpmArgs += "--strictPort"
    }

    Write-Host "Running npm script: $Script"
    & npm.cmd run $Script -- @effectiveNpmArgs
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
