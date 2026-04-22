param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $MavenArgs
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot "backend"
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

function Get-JavaMajorVersion {
    param([string] $JavaExe)

    $versionOutput = & cmd.exe /c "`"$JavaExe`" -version 2>&1"
    $firstLine = ($versionOutput | Select-Object -First 1).ToString()
    if ($firstLine -match 'version "1\.([0-9]+)') {
        return [int] $Matches[1]
    }
    if ($firstLine -match 'version "([0-9]+)') {
        return [int] $Matches[1]
    }
    return 0
}

function Test-JdkHome {
    param([string] $JdkHome)

    if ([string]::IsNullOrWhiteSpace($JdkHome)) {
        return $false
    }

    $javaExe = Join-Path $JdkHome "bin\java.exe"
    if (-not (Test-Path $javaExe)) {
        return $false
    }

    return (Get-JavaMajorVersion $javaExe) -ge 21
}

function Resolve-Jdk21Home {
    $candidateHomes = New-Object System.Collections.Generic.List[string]

    $preferredLocalHomes = @(
        (Join-Path $repoRoot "tools\jdk-21"),
        (Join-Path $repoRoot ".jdk\jdk-21")
    )

    foreach ($preferredHome in $preferredLocalHomes) {
        $candidateHomes.Add($preferredHome)
    }

    foreach ($root in @((Join-Path $repoRoot "tools"), (Join-Path $repoRoot ".jdk"))) {
        if (Test-Path $root) {
            Get-ChildItem -Path $root -Directory -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -like "jdk-21*" -or $_.Name -like "temurin-21*" } |
                ForEach-Object { $candidateHomes.Add($_.FullName) }
        }
    }

    foreach ($envHome in @($env:JAVA21_HOME, $env:JDK21_HOME, $env:JAVA_HOME)) {
        if (-not [string]::IsNullOrWhiteSpace($envHome)) {
            $candidateHomes.Add($envHome)
        }
    }

    foreach ($candidateHome in $candidateHomes) {
        if (Test-JdkHome $candidateHome) {
            return (Resolve-Path $candidateHome).Path
        }
    }

    return $null
}

$jdkHome = Resolve-Jdk21Home
if ($null -eq $jdkHome) {
    Write-Host "JDK 21 was not found." -ForegroundColor Red
    Write-Host ""
    Write-Host "Recommended setup:" -ForegroundColor Yellow
    Write-Host "1. Download a JDK 21 zip."
    Write-Host "2. Extract it into this repository as: tools\jdk-21"
    Write-Host "3. Confirm this file exists: tools\jdk-21\bin\java.exe"
    Write-Host "4. Run again: .\scripts\run-backend.cmd"
    Write-Host ""
    Write-Host "You can also set JAVA21_HOME or JDK21_HOME to an installed JDK 21."
    exit 1
}

$env:JAVA_HOME = $jdkHome
$env:Path = "$jdkHome\bin;$env:Path"

Import-DotEnvIfPresent $localGitLabEnv

Write-Host "Using JAVA_HOME=$env:JAVA_HOME"
& cmd.exe /c "`"$jdkHome\bin\java.exe`" -version 2>&1"

$argsToMaven = @("spring-boot:run")
if ($MavenArgs.Count -gt 0) {
    $argsToMaven = $MavenArgs
}

Push-Location $backendDir
try {
    & mvn.cmd @argsToMaven
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
