param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $MavenArgs
)

& (Join-Path $PSScriptRoot "run-backend.ps1") @MavenArgs
exit $LASTEXITCODE

