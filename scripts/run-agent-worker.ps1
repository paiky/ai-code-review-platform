param(
    [ValidateSet("start", "ensure", "status", "logs", "stop")]
    [string] $Action = "start",
    [ValidateRange(0, 300)]
    [int] $WaitForBackendSeconds = 0
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot "backend-python"
$envFile = Join-Path $repoRoot ".local\gitlab.env"
$composeFile = Join-Path $repoRoot "deploy\docker-compose.windows-agent.yml"
$secretInitializer = Join-Path $PSScriptRoot "init-agent-review-secrets.ps1"
$backendBaseUrl = "http://localhost:8090"
$proxyHostsFile = Join-Path $repoRoot ".local\agent-review-squid-hosts"
$proxyConfigFile = Join-Path $repoRoot ".local\agent-egress-squid.windows.conf"

function Import-DotEnv {
    param([string] $Path)
    if (-not (Test-Path -LiteralPath $Path)) { return }
    Get-Content -LiteralPath $Path -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if ([string]::IsNullOrWhiteSpace($line) -or $line.StartsWith("#")) { return }
        $separatorIndex = $line.IndexOf("=")
        if ($separatorIndex -le 0) { return }
        $key = $line.Substring(0, $separatorIndex).Trim()
        $value = $line.Substring($separatorIndex + 1).Trim()
        if ($value.Length -ge 2 -and (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'")))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        [Environment]::SetEnvironmentVariable($key, $value, "Process")
    }
}

function Invoke-DockerCompose {
    param([string[]] $Arguments)
    & docker compose --project-name ai-code-review-windows-agent --env-file $envFile -f $composeFile @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose command failed with exit code $LASTEXITCODE." }
}

function Get-AgentSettings {
    try { return (Invoke-RestMethod -Uri "$backendBaseUrl/api/code-quality-reviews/agent-settings" -TimeoutSec 5).data }
    catch { return $null }
}

function Test-AgentWorkerOnline {
    param(
        $Settings,
        [string] $WorkerId,
        [string] $WorkerPrefix
    )
    if ($null -eq $Settings -or $Settings.workerStatus -ne "ONLINE") { return $false }
    $nodes = @($Settings.workerPool.nodes)
    if ($nodes.Count -gt 0) {
        if (-not [string]::IsNullOrWhiteSpace($WorkerId)) {
            return $null -ne ($nodes | Where-Object {
                $_.online -eq $true -and $_.state -ne "DRAINING" -and $_.workerId -eq $WorkerId
            } | Select-Object -First 1)
        }
        $prefix = "$WorkerPrefix-"
        return $null -ne ($nodes | Where-Object {
            $_.online -eq $true -and $_.state -ne "DRAINING" -and $_.workerId.StartsWith($prefix)
        } | Select-Object -First 1)
    }
    if (-not [string]::IsNullOrWhiteSpace($WorkerId)) {
        return $Settings.workerId -eq $WorkerId
    }
    return -not [string]::IsNullOrWhiteSpace($Settings.workerId) -and $Settings.workerId.StartsWith("$WorkerPrefix-")
}

function Write-AgentEgressProxyConfig {
    param([string] $Path)

    $lines = [System.Collections.Generic.List[string]]::new()
    @(
        "http_port 3128",
        "pid_filename none",
        "hosts_file /etc/squid/hosts.windows",
        "",
        "acl CONNECT method CONNECT",
        "acl SSL_ports port 443",
        "acl windows_backend dstdomain host.docker.internal",
        "acl windows_backend_port port 8090",
        "",
        "http_access allow CONNECT SSL_ports",
        "http_access allow windows_backend windows_backend_port",
        "http_access deny all",
        "",
        "always_direct allow windows_backend"
    ) | ForEach-Object { $lines.Add($_) }

    $upstreamSetting = $env:AGENT_REVIEW_UPSTREAM_PROXY
    if (-not [string]::IsNullOrWhiteSpace($upstreamSetting)) {
        $candidate = $upstreamSetting.Trim()
        if (-not $candidate.Contains("://")) { $candidate = "http://$candidate" }
        $uri = $null
        if (-not [Uri]::TryCreate($candidate, [UriKind]::Absolute, [ref] $uri) -or
            $uri.Scheme -ne "http" -or
            [string]::IsNullOrWhiteSpace($uri.Host) -or
            $uri.Port -lt 1 -or
            $uri.Port -gt 65535 -or
            $uri.AbsolutePath -ne "/" -or
            -not [string]::IsNullOrWhiteSpace($uri.Query) -or
            -not [string]::IsNullOrWhiteSpace($uri.UserInfo)) {
            throw "AGENT_REVIEW_UPSTREAM_PROXY must be an HTTP proxy in host:port or http://host:port form without credentials or a path."
        }
        $lines.Add("cache_peer $($uri.Host) parent $($uri.Port) 0 no-query default name=lan_upstream")
        $lines.Add("cache_peer_access lan_upstream allow CONNECT SSL_ports")
        $lines.Add("cache_peer_access lan_upstream deny all")
        $lines.Add("never_direct allow CONNECT SSL_ports")
    }

    @(
        "",
        "access_log none",
        "cache_log /dev/null",
        "cache_store_log none",
        "cache deny all",
        "forwarded_for delete",
        ""
    ) | ForEach-Object { $lines.Add($_) }
    $utf8WithoutBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, [string]::Join("`n", $lines), $utf8WithoutBom)
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker command was not found. Install Docker Desktop and use Linux containers."
}
docker version --format "{{.Server.Version}}" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Docker Engine is unavailable. Start Docker Desktop and wait for the Linux engine." }

Import-DotEnv $envFile
if ($Action -in @("start", "ensure") -and (
    [string]::IsNullOrWhiteSpace($env:AGENT_REVIEW_CONFIG_ENCRYPTION_KEY) -or
    [string]::IsNullOrWhiteSpace($env:AGENT_REVIEW_WORKER_TOKEN)
)) {
    & $secretInitializer -EnvFile $envFile
    Import-DotEnv $envFile
}
if ([string]::IsNullOrWhiteSpace($env:AGENT_REVIEW_WORKER_TOKEN)) {
    throw "AGENT_REVIEW_WORKER_TOKEN is missing from .local/gitlab.env."
}

$workspaceSetting = $env:LOCAL_REPO_WORKSPACE_ROOT
if ([string]::IsNullOrWhiteSpace($workspaceSetting)) { $workspaceSetting = ".local/review-workspaces" }
if ([System.IO.Path]::IsPathRooted($workspaceSetting)) {
    $workspacePath = [System.IO.Path]::GetFullPath($workspaceSetting)
}
else {
    $workspacePath = [System.IO.Path]::GetFullPath((Join-Path $backendDir $workspaceSetting))
}
if ($Action -in @("start", "ensure") -and -not (Test-Path -LiteralPath $workspacePath)) {
    New-Item -ItemType Directory -Path $workspacePath -Force | Out-Null
}
$env:LOCAL_REPO_WORKSPACE_HOST_DIR = $workspacePath.Replace("\", "/")
$env:AGENT_REVIEW_WINDOWS_PROXY_HOSTS_FILE = $proxyHostsFile.Replace("\", "/")
$env:AGENT_REVIEW_WINDOWS_PROXY_CONFIG_FILE = $proxyConfigFile.Replace("\", "/")
$expectedWorkerId = if ([string]::IsNullOrWhiteSpace($env:AGENT_REVIEW_WORKER_ID)) { "" } else { $env:AGENT_REVIEW_WORKER_ID.Trim() }
$expectedWorkerPrefix = if ([string]::IsNullOrWhiteSpace($env:AGENT_REVIEW_WORKER_ID_PREFIX)) { "windows-agent-worker" } else { $env:AGENT_REVIEW_WORKER_ID_PREFIX.Trim() }
$env:AGENT_REVIEW_WORKER_ID_PREFIX = $expectedWorkerPrefix

switch ($Action) {
    { $_ -in @("start", "ensure") } {
        $backendReady = $false
        $deadline = [DateTime]::UtcNow.AddSeconds($WaitForBackendSeconds)
        do {
            try {
                Invoke-RestMethod -Uri "$backendBaseUrl/api/health" -TimeoutSec 5 | Out-Null
                $backendReady = $true
            }
            catch {
                if ([DateTime]::UtcNow -lt $deadline) { Start-Sleep -Seconds 2 }
            }
        } while (-not $backendReady -and [DateTime]::UtcNow -lt $deadline)
        if (-not $backendReady) { throw "The local backend is not reachable at $backendBaseUrl. Start it with .\scripts\run-backend.cmd dev first." }

        if ($Action -eq "ensure") {
            $existingSettings = Get-AgentSettings
            $runningServices = @(& docker compose --project-name ai-code-review-windows-agent --env-file $envFile -f $composeFile ps --status running --services 2>$null)
            $workerRunning = $runningServices -contains "agent-worker"
            $proxyRunning = $runningServices -contains "agent-egress-proxy"
            if ($null -ne $existingSettings -and
                (Test-AgentWorkerOnline -Settings $existingSettings -WorkerId $expectedWorkerId -WorkerPrefix $expectedWorkerPrefix) -and
                $workerRunning -and
                $proxyRunning) {
                Write-Host "Agent Worker is already ONLINE."
                exit 0
            }
        }
        $utf8WithoutBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($proxyHostsFile, "127.0.0.1 localhost`n", $utf8WithoutBom)
        Write-AgentEgressProxyConfig -Path $proxyConfigFile
        $workerImage = "ai-code-review-windows-agent-agent-worker"
        $proxyImage = "ai-code-review-windows-agent-agent-egress-proxy"
        $imagesAvailable = $true
        foreach ($imageName in @($workerImage, $proxyImage)) {
            & docker image inspect $imageName *> $null
            if ($LASTEXITCODE -ne 0) { $imagesAvailable = $false }
        }
        if ($Action -eq "start" -or -not $imagesAvailable) {
            Invoke-DockerCompose @("build", "agent-egress-proxy", "agent-worker")
        }
        $gatewayOutput = & docker run --rm --add-host "host.docker.internal:host-gateway" --entrypoint getent $proxyImage ahostsv4 host.docker.internal
        if ($LASTEXITCODE -ne 0 -or -not $gatewayOutput) { throw "Could not resolve the Docker Desktop IPv4 host gateway." }
        $gatewayAddress = (($gatewayOutput | Select-Object -First 1).Trim() -split "\s+")[0]
        $parsedGatewayAddress = $null
        if (-not [System.Net.IPAddress]::TryParse($gatewayAddress, [ref] $parsedGatewayAddress) -or $parsedGatewayAddress.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) {
            throw "Docker Desktop returned an invalid IPv4 host gateway."
        }
        [System.IO.File]::WriteAllText($proxyHostsFile, "$gatewayAddress host.docker.internal`n", $utf8WithoutBom)
        Invoke-DockerCompose @("up", "-d", "--force-recreate")
        Write-Host "Waiting for Agent Worker heartbeat..."
        for ($attempt = 0; $attempt -lt 30; $attempt++) {
            $settings = Get-AgentSettings
            if ($null -ne $settings -and
                (Test-AgentWorkerOnline -Settings $settings -WorkerId $expectedWorkerId -WorkerPrefix $expectedWorkerPrefix)) {
                Write-Host "Agent Worker is ONLINE. Workspace: $workspacePath"
                exit 0
            }
            Start-Sleep -Seconds 2
        }
        Invoke-DockerCompose @("ps")
        throw "Agent Worker did not become ONLINE within 60 seconds. Run .\scripts\run-agent-worker.cmd logs and confirm the backend was restarted after the Worker token was initialized."
    }
    "status" {
        Invoke-DockerCompose @("ps")
        $settings = Get-AgentSettings
        if ($null -eq $settings) { Write-Host "Local backend is unreachable at $backendBaseUrl." }
        else {
            Write-Host "Backend reports Worker Pool $($settings.workerStatus); online=$($settings.workerPool.onlineCount); acceptingCapacity=$($settings.queueMetrics.onlineCapacity); busyCapacity=$($settings.queueMetrics.busyCapacity); utilization=$($settings.queueMetrics.utilizationPercent)%; draining=$($settings.queueMetrics.drainingWorkers); queued=$($settings.queueMetrics.queued)"
        }
    }
    "logs" { Invoke-DockerCompose @("logs", "--tail=100", "agent-worker", "agent-egress-proxy") }
    "stop" {
        Write-Host "Stopping Agent Worker with SIGTERM draining; an active task may use up to the fixed 930-second grace period."
        Invoke-DockerCompose @("down")
    }
}
