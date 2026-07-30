[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int] $FrontendPort = 5173,
    [ValidateRange(1, 65535)]
    [int] $MockPort = 8080,
    [ValidateRange(5, 120)]
    [int] $ReadyTimeoutSeconds = 30,
    [switch] $Stop
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$localRoot = Join-Path $repoRoot ".local\docs50-acceptance"
$statePath = Join-Path $localRoot "state-$FrontendPort-$MockPort.json"
$frontendScript = Join-Path $PSScriptRoot "run-frontend.ps1"
$mockScript = Join-Path $PSScriptRoot "docs50-mock-server.mjs"
$detachedLauncher = Join-Path $PSScriptRoot "start-detached.mjs"
$healthPath = "/api/__docs50__/health"
$healthService = "docs50-safe-mock"

function Get-ListeningProcessId {
    param([int] $PortNumber)

    $pattern = "^\s*TCP\s+\S+:$PortNumber\s+\S+\s+LISTENING\s+(\d+)\s*$"
    foreach ($line in (& netstat.exe -ano -p TCP)) {
        if ($line -match $pattern) {
            return [int] $Matches[1]
        }
    }
    return $null
}

function Test-ProcessAlive {
    param([Nullable[int]] $ProcessId)

    if ($null -eq $ProcessId) {
        return $false
    }
    return $null -ne (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)
}

function Get-HealthService {
    param([string] $Uri)

    try {
        $response = Invoke-RestMethod -Uri $Uri -Method Get -TimeoutSec 2
        return [string] $response.data.service
    }
    catch {
        return ""
    }
}

function Test-MockReady {
    param([int] $PortNumber)

    return (Get-HealthService "http://127.0.0.1:$PortNumber$healthPath") -eq $healthService
}

function Test-FrontendRootReady {
    param([int] $PortNumber)

    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$PortNumber/" -TimeoutSec 2
        return $response.StatusCode -eq 200 -and $response.Content.Contains('id="root"')
    }
    catch {
        return $false
    }
}

function Test-FrontendProxyReady {
    param([int] $PortNumber)

    return (Get-HealthService "http://127.0.0.1:$PortNumber$healthPath") -eq $healthService
}

function Start-DetachedCommand {
    param(
        [string] $FilePath,
        [string[]] $ArgumentList,
        [string] $WorkingDirectory,
        [string] $StdoutPath,
        [string] $StderrPath
    )

    $nodePath = (Get-Command node.exe -ErrorAction Stop).Source
    $launcherOutput = & $nodePath `
        $detachedLauncher `
        "--cwd" $WorkingDirectory `
        "--stdout" $StdoutPath `
        "--stderr" $StderrPath `
        "--" `
        $FilePath `
        @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        throw "Detached process launcher failed for $FilePath."
    }
    $launcherResult = ($launcherOutput | Select-Object -Last 1) | ConvertFrom-Json
    $launcherPid = [int] $launcherResult.pid
    if ($launcherPid -le 0) {
        throw "Detached process launcher did not return a valid PID for $FilePath."
    }
    return $launcherPid
}

function Stop-RecordedService {
    param(
        [pscustomobject] $Service,
        [string] $Name
    )

    if ($null -eq $Service -or [bool] $Service.reused) {
        Write-Host "Keeping reused $Name service."
        return
    }

    $currentOwner = Get-ListeningProcessId ([int] $Service.port)
    if ($null -ne $currentOwner -and $currentOwner -eq [int] $Service.pid) {
        Stop-Process -Id $currentOwner -ErrorAction Stop
        Write-Host "Stopped $Name service PID $currentOwner on port $($Service.port)."
    }
    else {
        Write-Host "Skipped $Name service stop because recorded PID no longer owns port $($Service.port)."
    }

    $launcherPid = [int] $Service.launcherPid
    if ($launcherPid -gt 0) {
        for ($attempt = 0; $attempt -lt 8 -and (Test-ProcessAlive $launcherPid); $attempt += 1) {
            Start-Sleep -Milliseconds 250
        }
        if (Test-ProcessAlive $launcherPid) {
            Stop-Process -Id $launcherPid -ErrorAction SilentlyContinue
        }
    }
}

function Read-LogTail {
    param([string] $Path)

    if (-not (Test-Path $Path)) {
        return "(log not created)"
    }
    return (Get-Content -Path $Path -Tail 25 -Encoding UTF8) -join [Environment]::NewLine
}

if ($Stop) {
    if (-not (Test-Path $statePath)) {
        Write-Host "No docs/50 acceptance state found for frontend $FrontendPort and mock $MockPort."
        exit 0
    }
    $state = Get-Content -Raw -Encoding UTF8 $statePath | ConvertFrom-Json
    Stop-RecordedService $state.frontend "frontend"
    Stop-RecordedService $state.mock "mock"
    $state.ready = $false
    $state | Add-Member `
        -NotePropertyName "stoppedAt" `
        -NotePropertyValue (Get-Date).ToUniversalTime().ToString("o") `
        -Force
    $state | ConvertTo-Json -Depth 5 | Set-Content -Path $statePath -Encoding UTF8
    exit 0
}

if ($FrontendPort -eq $MockPort) {
    throw "FrontendPort and MockPort must be different."
}
if (-not (Test-Path $frontendScript)) {
    throw "Frontend launcher was not found: $frontendScript"
}
if (-not (Test-Path $mockScript)) {
    throw "docs/50 mock server was not found: $mockScript"
}
if (-not (Test-Path $detachedLauncher)) {
    throw "Detached process launcher was not found: $detachedLauncher"
}

New-Item -ItemType Directory -Path $localRoot -Force | Out-Null
$frontendOut = Join-Path $localRoot "frontend-$FrontendPort.out.log"
$frontendErr = Join-Path $localRoot "frontend-$FrontendPort.err.log"
$mockOut = Join-Path $localRoot "mock-$MockPort.out.log"
$mockErr = Join-Path $localRoot "mock-$MockPort.err.log"

$mockLauncherPid = 0
$frontendLauncherPid = 0
$mockStarted = $false
$frontendStarted = $false
$mockPid = Get-ListeningProcessId $MockPort
$frontendPid = Get-ListeningProcessId $FrontendPort

try {
    if ($null -ne $mockPid) {
        if (-not (Test-MockReady $MockPort)) {
            throw "Mock port $MockPort is occupied by PID $mockPid but does not expose the docs/50 safe health marker."
        }
        Write-Host "Reusing docs/50 mock PID $mockPid on port $MockPort."
    }
    else {
        $nodePath = (Get-Command node.exe -ErrorAction Stop).Source
        $mockLauncherPid = Start-DetachedCommand `
            -FilePath $nodePath `
            -ArgumentList @($mockScript, "--port", [string] $MockPort) `
            -WorkingDirectory $repoRoot `
            -StdoutPath $mockOut `
            -StderrPath $mockErr
        $mockStarted = $true
        Write-Host "Started docs/50 mock launcher PID $mockLauncherPid."
    }

    if ($null -ne $frontendPid) {
        if (-not (Test-FrontendRootReady $FrontendPort) -or -not (Test-FrontendProxyReady $FrontendPort)) {
            throw "Frontend port $FrontendPort is occupied by PID $frontendPid but is not wired to the docs/50 safe mock."
        }
        Write-Host "Reusing docs/50 frontend PID $frontendPid on port $FrontendPort."
    }
    else {
        $powershellPath = (Get-Command powershell.exe -ErrorAction Stop).Source
        $mockTarget = "http://127.0.0.1:$MockPort"
        $frontendLauncherPid = Start-DetachedCommand `
            -FilePath $powershellPath `
            -ArgumentList @(
                "-NoProfile",
                "-ExecutionPolicy", "Bypass",
                "-File", $frontendScript,
                "-Script", "dev",
                "-ApiProxyTarget", $mockTarget,
                "-HostAddress", "127.0.0.1",
                "-Port", [string] $FrontendPort,
                "-StrictPort"
            ) `
            -WorkingDirectory $repoRoot `
            -StdoutPath $frontendOut `
            -StderrPath $frontendErr
        $frontendStarted = $true
        Write-Host "Started frontend launcher PID $frontendLauncherPid."
    }

    $deadline = (Get-Date).AddSeconds($ReadyTimeoutSeconds)
    $ready = $false
    while ((Get-Date) -lt $deadline) {
        $mockPid = Get-ListeningProcessId $MockPort
        $frontendPid = Get-ListeningProcessId $FrontendPort
        $mockLauncherHealthy = -not $mockStarted -or (Test-ProcessAlive $mockLauncherPid) -or $null -ne $mockPid
        $frontendLauncherHealthy = -not $frontendStarted -or (Test-ProcessAlive $frontendLauncherPid) -or $null -ne $frontendPid
        if (
            $mockLauncherHealthy `
            -and $frontendLauncherHealthy `
            -and $null -ne $mockPid `
            -and $null -ne $frontendPid `
            -and (Test-MockReady $MockPort) `
            -and (Test-FrontendRootReady $FrontendPort) `
            -and (Test-FrontendProxyReady $FrontendPort)
        ) {
            $ready = $true
            break
        }
        Start-Sleep -Milliseconds 250
    }

    if (-not $ready) {
        throw "docs/50 acceptance services did not become ready within $ReadyTimeoutSeconds seconds."
    }

    $state = [ordered] @{
        ready = $true
        checkedAt = (Get-Date).ToUniversalTime().ToString("o")
        frontend = [ordered] @{
            url = "http://127.0.0.1:$FrontendPort"
            port = $FrontendPort
            pid = $frontendPid
            launcherPid = $frontendLauncherPid
            reused = -not $frontendStarted
            stdout = $frontendOut
            stderr = $frontendErr
        }
        mock = [ordered] @{
            url = "http://127.0.0.1:$MockPort"
            port = $MockPort
            pid = $mockPid
            launcherPid = $mockLauncherPid
            reused = -not $mockStarted
            stdout = $mockOut
            stderr = $mockErr
        }
    }
    $state | ConvertTo-Json -Depth 5 | Set-Content -Path $statePath -Encoding UTF8
    Write-Host "DOCS50_ACCEPTANCE_READY"
    Write-Host "FRONTEND_URL=$($state.frontend.url)"
    Write-Host "FRONTEND_PID=$($state.frontend.pid)"
    Write-Host "MOCK_URL=$($state.mock.url)"
    Write-Host "MOCK_PID=$($state.mock.pid)"
    Write-Host "STATE_FILE=$statePath"
}
catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    if ($frontendStarted) {
        $owner = Get-ListeningProcessId $FrontendPort
        if ($null -ne $owner) {
            Stop-Process -Id $owner -ErrorAction SilentlyContinue
        }
        if (Test-ProcessAlive $frontendLauncherPid) {
            Stop-Process -Id $frontendLauncherPid -ErrorAction SilentlyContinue
        }
    }
    if ($mockStarted) {
        $owner = Get-ListeningProcessId $MockPort
        if ($null -ne $owner) {
            Stop-Process -Id $owner -ErrorAction SilentlyContinue
        }
        if (Test-ProcessAlive $mockLauncherPid) {
            Stop-Process -Id $mockLauncherPid -ErrorAction SilentlyContinue
        }
    }
    Write-Host "Frontend log tail:"
    Write-Host (Read-LogTail $frontendOut)
    Write-Host "Mock log tail:"
    Write-Host (Read-LogTail $mockOut)
    exit 1
}
