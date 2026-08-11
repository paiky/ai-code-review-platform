param(
    [Parameter(Position = 0)]
    [ValidateSet("plan", "apply")]
    [string] $Action = "plan",
    [Parameter(Position = 1)]
    [ValidateSet("local", "test")]
    [string] $Target = "local",
    [switch] $ConfirmWrite,
    [switch] $ConfirmTest
)

$ErrorActionPreference = "Stop"
$backendRunner = Join-Path $PSScriptRoot "run-backend.ps1"
if (-not (Test-Path -LiteralPath $backendRunner)) {
    throw "Python backend runner was not found: $backendRunner"
}

$arguments = [System.Collections.Generic.List[string]]::new()
$arguments.Add("app.database_baseline_reconcile_cli")
$arguments.Add($Action)
$arguments.Add($Target)
if ($ConfirmWrite) { $arguments.Add("--confirm-write") }
if ($ConfirmTest) { $arguments.Add("--confirm-test") }

& $backendRunner @arguments
exit $LASTEXITCODE
