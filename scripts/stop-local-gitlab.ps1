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
if ([string]::IsNullOrWhiteSpace($env:DOCKER_CONFIG)) {
    $env:DOCKER_CONFIG = (Resolve-Path $dockerConfig).Path
}

docker compose --env-file $EnvFile -f $composeFile down

Write-Host "Local GitLab container stopped. Data remains under .local\gitlab."
