param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $Args
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot "backend-python"
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

function Resolve-PythonCommand {
    $venvPython = Join-Path $backendDir ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return @($venvPython)
    }

    if (-not [string]::IsNullOrWhiteSpace($env:PYTHON_EXECUTABLE)) {
        return @($env:PYTHON_EXECUTABLE)
    }

    $python = Get-Command python -All -ErrorAction SilentlyContinue |
        Where-Object { $_.Source -notlike "*\Microsoft\WindowsApps\python.exe" } |
        Select-Object -First 1
    if ($null -ne $python) {
        return @($python.Source)
    }

    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($null -ne $pyLauncher) {
        return @("py", "-3.12")
    }

    throw "Python 3.12 was not found. Install Python 3.12 or set PYTHON_EXECUTABLE."
}

function Invoke-Python {
    param([string[]] $PythonCommand, [string[]] $PythonArgs)

    $exe = $PythonCommand[0]
    $prefixArgs = @()
    if ($PythonCommand.Count -gt 1) {
        $prefixArgs = $PythonCommand[1..($PythonCommand.Count - 1)]
    }

    & $exe @prefixArgs @PythonArgs
    $script:exitCode = $LASTEXITCODE
}

if (-not (Test-Path $backendDir)) {
    throw "backend-python directory was not found: $backendDir"
}

Import-DotEnvIfPresent $localGitLabEnv

$pythonCommand = Resolve-PythonCommand
$command = "dev"
if ($Args.Count -gt 0) {
    $command = $Args[0]
}

$remainingArgs = @()
if ($Args.Count -gt 1) {
    $remainingArgs = $Args[1..($Args.Count - 1)]
}

$exitCode = 0
Push-Location $backendDir
try {
    switch ($command) {
        "test" {
            Invoke-Python -PythonCommand $pythonCommand -PythonArgs (@("-m", "pytest") + $remainingArgs)
        }
        "lint" {
            Invoke-Python -PythonCommand $pythonCommand -PythonArgs (@("-m", "ruff", "check", ".") + $remainingArgs)
        }
        "dev" {
            $port = $env:SERVER_PORT
            if ([string]::IsNullOrWhiteSpace($port)) {
                $port = "18080"
            }
            Invoke-Python -PythonCommand $pythonCommand -PythonArgs (@("-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", $port, "--reload") + $remainingArgs)
        }
        default {
            Invoke-Python -PythonCommand $pythonCommand -PythonArgs (@("-m") + $Args)
        }
    }
}
finally {
    Pop-Location
}

exit $exitCode
