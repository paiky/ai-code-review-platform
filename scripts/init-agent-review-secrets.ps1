param(
    [string] $EnvFile
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($EnvFile)) {
    $EnvFile = Join-Path $repoRoot ".local\gitlab.env"
}
$EnvFile = [System.IO.Path]::GetFullPath($EnvFile)

function New-UrlSafeSecret {
    param([int] $ByteCount)

    $bytes = New-Object byte[] $ByteCount
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
    }
    finally {
        $generator.Dispose()
    }
    return [Convert]::ToBase64String($bytes).Replace("+", "-").Replace("/", "_")
}

function Get-UnquotedValue {
    param([string] $Line)

    $separatorIndex = $Line.IndexOf("=")
    if ($separatorIndex -lt 0) {
        return ""
    }
    $value = $Line.Substring($separatorIndex + 1).Trim()
    if ($value.Length -ge 2 -and (
        ($value.StartsWith('"') -and $value.EndsWith('"')) -or
        ($value.StartsWith("'") -and $value.EndsWith("'"))
    )) {
        return $value.Substring(1, $value.Length - 2).Trim()
    }
    return $value
}

$lines = New-Object System.Collections.Generic.List[string]
if (Test-Path -LiteralPath $EnvFile) {
    Get-Content -LiteralPath $EnvFile -Encoding UTF8 | ForEach-Object { $lines.Add($_) }
}

$changed = $false
$specifications = @(
    @{ Name = "AGENT_REVIEW_CONFIG_ENCRYPTION_KEY"; ByteCount = 32 },
    @{ Name = "AGENT_REVIEW_WORKER_TOKEN"; ByteCount = 48 }
)

foreach ($specification in $specifications) {
    $name = $specification.Name
    $matchingIndexes = @()
    $hasNonEmptyValue = $false
    for ($index = 0; $index -lt $lines.Count; $index++) {
        if ($lines[$index] -match "^\s*$([regex]::Escape($name))\s*=") {
            $matchingIndexes += $index
            if (-not [string]::IsNullOrWhiteSpace((Get-UnquotedValue $lines[$index]))) {
                $hasNonEmptyValue = $true
            }
        }
    }

    if ($hasNonEmptyValue) {
        Write-Host "$name already configured; keeping the existing value."
        continue
    }

    $secret = New-UrlSafeSecret -ByteCount $specification.ByteCount
    if ($matchingIndexes.Count -eq 0) {
        $lines.Add("$name=$secret")
    }
    else {
        foreach ($matchingIndex in $matchingIndexes) {
            $lines[$matchingIndex] = "$name=$secret"
        }
    }
    $changed = $true
    Write-Host "$name initialized without printing its value."
}

if ($changed) {
    $parentDirectory = Split-Path -Parent $EnvFile
    if (-not (Test-Path -LiteralPath $parentDirectory)) {
        New-Item -ItemType Directory -Path $parentDirectory -Force | Out-Null
    }
    $utf8WithoutBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllLines($EnvFile, $lines, $utf8WithoutBom)
    Write-Host "Agent Review infrastructure secrets were written to $EnvFile."
}
else {
    Write-Host "Agent Review infrastructure secrets are already configured in $EnvFile."
}

Write-Host "Restart the backend process before saving the Agent DeepSeek API Key."
