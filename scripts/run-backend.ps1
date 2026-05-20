param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $Args
)

$ErrorActionPreference = "Stop"

$pythonScript = Join-Path $PSScriptRoot "run-backend-python.ps1"
if (-not (Test-Path $pythonScript)) {
    throw "Python backend runner was not found: $pythonScript"
}

& $pythonScript @Args
exit $LASTEXITCODE
