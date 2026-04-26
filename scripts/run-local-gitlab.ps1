param(
    [string] $EnvFile
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $repoRoot "local-gitlab\docker-compose.yml"
if ([string]::IsNullOrWhiteSpace($EnvFile)) {
    $defaultEnvFile = Join-Path $repoRoot ".local\local-gitlab.env"
    if (Test-Path $defaultEnvFile) {
        $EnvFile = $defaultEnvFile
    } else {
        $EnvFile = Join-Path $repoRoot "local-gitlab\.env.example"
    }
}

$dockerConfig = Join-Path $repoRoot ".local\docker-config"
New-Item -ItemType Directory -Force -Path $dockerConfig | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $repoRoot ".local\gitlab\config") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $repoRoot ".local\gitlab\logs") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $repoRoot ".local\gitlab\data") | Out-Null

if ([string]::IsNullOrWhiteSpace($env:DOCKER_CONFIG)) {
    $env:DOCKER_CONFIG = (Resolve-Path $dockerConfig).Path
}

Write-Host "Using compose file: $composeFile"
Write-Host "Using env file: $EnvFile"
Write-Host "Using Docker config: $env:DOCKER_CONFIG"

try {
    docker version | Out-Host
} catch {
    Write-Host "Docker daemon is not available." -ForegroundColor Red
    Write-Host "Start Docker Desktop and make sure your Windows user can access Docker daemon."
    Write-Host "If you see Access is denied, add your Windows user to the docker-users group and sign out/in."
    throw
}

docker compose --env-file $EnvFile -f $composeFile up -d

Write-Host ""
Write-Host "Local GitLab is starting." -ForegroundColor Green
Write-Host "URL: http://localhost:8929"
Write-Host "Default username: root"
Write-Host "Default password: LocalGitLab@123456"
Write-Host ""
Write-Host "First startup can take 5-10 minutes. Follow logs with:"
Write-Host "  docker logs -f ai-code-review-local-gitlab"
