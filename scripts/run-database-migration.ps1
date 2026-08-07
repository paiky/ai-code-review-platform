param(
    [Parameter(Position = 0)]
    [ValidateSet("status", "dry-run", "baseline", "apply", "verify")]
    [string] $Action = "status",
    [Parameter(Position = 1)]
    [ValidateSet("local", "test")]
    [string] $Target = "local",
    [switch] $ConfirmTest
)

$ErrorActionPreference = "Stop"
$backendRunner = Join-Path $PSScriptRoot "run-backend-python.ps1"
if (-not (Test-Path -LiteralPath $backendRunner)) {
    throw "Python backend runner was not found: $backendRunner"
}

$arguments = [System.Collections.Generic.List[string]]::new()
$arguments.Add("app.database_migration_cli")
$arguments.Add($Action)
$arguments.Add($Target)
if ($ConfirmTest) {
    $arguments.Add("--confirm-test")
}

& $backendRunner @arguments
exit $LASTEXITCODE
