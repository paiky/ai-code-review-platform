param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $Args
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot "backend-python"
$localGitLabEnv = Join-Path $repoRoot ".local\gitlab.env"
$agentWorkerScript = Join-Path $PSScriptRoot "run-agent-worker.ps1"

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

function Enable-BackendPythonStartupHooks {
    $env:AI_REVIEW_SKIP_PYTHON_WMI = "1"

    if ([string]::IsNullOrWhiteSpace($env:PYTHONPATH)) {
        $env:PYTHONPATH = $backendDir
        return
    }

    $pathSeparator = [System.IO.Path]::PathSeparator
    $pythonPaths = $env:PYTHONPATH -split [regex]::Escape([string] $pathSeparator)
    if ($pythonPaths -notcontains $backendDir) {
        $env:PYTHONPATH = "$backendDir$pathSeparator$env:PYTHONPATH"
    }
}

function Start-AgentReviewWorkerIfConfigured {
    param([string] $BackendPort)

    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { return }
    if ($env:AGENT_REVIEW_AUTO_START_WORKER -and $env:AGENT_REVIEW_AUTO_START_WORKER.Trim().ToLowerInvariant() -eq "false") {
        Write-Host "Agent Worker auto-start is disabled by AGENT_REVIEW_AUTO_START_WORKER=false."
        return
    }
    if ([string]::IsNullOrWhiteSpace($env:AGENT_REVIEW_WORKER_TOKEN)) { return }
    if ($BackendPort -ne "8090") {
        Write-Warning "Agent Worker auto-start only supports the secured local backend port 8090; current port is $BackendPort."
        return
    }
    if (-not (Test-Path -LiteralPath $agentWorkerScript) -or -not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Warning "Agent Worker auto-start was skipped because its script or Docker CLI is unavailable."
        return
    }

    $localDirectory = Join-Path $repoRoot ".local"
    New-Item -ItemType Directory -Path $localDirectory -Force | Out-Null
    $logSuffix = Get-Date -Format "yyyyMMdd-HHmmss-fff"
    $stdoutLog = Join-Path $localDirectory "agent-worker-startup-$logSuffix.out.log"
    $stderrLog = Join-Path $localDirectory "agent-worker-startup-$logSuffix.err.log"

    $powershell = (Get-Command powershell.exe -ErrorAction Stop).Source
    $arguments = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", "`"$agentWorkerScript`"",
        "ensure",
        "-WaitForBackendSeconds", "60"
    )
    Start-Process -FilePath $powershell -ArgumentList $arguments -WorkingDirectory $repoRoot -WindowStyle Hidden -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog | Out-Null
    Write-Host "Agent Worker auto-start scheduled; logs: $stdoutLog and $stderrLog"
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

function Resolve-DevPort {
    param(
        [string[]] $CommandArgs,
        [string] $DefaultPort
    )

    $port = $DefaultPort
    $remaining = New-Object System.Collections.Generic.List[string]

    for ($index = 0; $index -lt $CommandArgs.Count; $index++) {
        $arg = $CommandArgs[$index]
        if ($arg -eq "--port" -and $index + 1 -lt $CommandArgs.Count) {
            $port = $CommandArgs[$index + 1]
            $index++
            continue
        }
        $remaining.Add($arg)
    }

    return @{
        Port = $port
        RemainingArgs = $remaining.ToArray()
    }
}

if (-not (Test-Path $backendDir)) {
    throw "backend-python directory was not found: $backendDir"
}

Import-DotEnvIfPresent $localGitLabEnv
Enable-BackendPythonStartupHooks

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
        "migrate" {
            Invoke-Python -PythonCommand $pythonCommand -PythonArgs (@("-m", "app.migrate") + $remainingArgs)
        }
        "dev" {
            $port = $env:SERVER_PORT
            if ([string]::IsNullOrWhiteSpace($port)) {
                $port = "8090"
            }
            $resolvedDev = Resolve-DevPort -CommandArgs $remainingArgs -DefaultPort $port
            Start-AgentReviewWorkerIfConfigured -BackendPort $resolvedDev.Port
            Invoke-Python -PythonCommand $pythonCommand -PythonArgs (@("-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", $resolvedDev.Port, "--reload") + $resolvedDev.RemainingArgs)
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
