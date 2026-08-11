param(
    [Parameter(Position = 0)]
    [ValidateSet("plan", "apply")]
    [string] $Action = "plan",
    [switch] $ConfirmCopy,
    [switch] $ConfirmSourceData
)

$ErrorActionPreference = "Stop"
$backendRunner = Join-Path $PSScriptRoot "run-backend.ps1"
if (-not (Test-Path -LiteralPath $backendRunner)) {
    throw "Python backend runner was not found: $backendRunner"
}

$arguments = [System.Collections.Generic.List[string]]::new()
$arguments.Add("app.database_data_copy_cli")
$arguments.Add($Action)
if ($ConfirmCopy) { $arguments.Add("--confirm-copy") }
if ($ConfirmSourceData) { $arguments.Add("--confirm-source-data") }

& $backendRunner @arguments
exit $LASTEXITCODE
