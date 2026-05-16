param(
  [string]$Version = (Get-Date -Format "yyyyMMddHHmmss"),
  [switch]$IncludeMysqlImage
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
$DeployDir = Join-Path $RepoRoot "deploy"
$OutputDir = Join-Path $RepoRoot ".local\docker-deploy\$Version"

$BackendImage = "ai-code-review-backend:$Version"
$FrontendImage = "ai-code-review-frontend:$Version"
$MysqlImage = "mysql:8.4"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  throw "Docker command was not found. Install Docker Desktop, start it, then reopen PowerShell or Cursor before running this script."
}

function Invoke-Docker {
  $Arguments = $args
  & docker @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "Docker command failed with exit code ${LASTEXITCODE}: docker $($Arguments -join ' ')"
  }
}

$DockerVersionOutput = docker version 2>&1
if ($LASTEXITCODE -ne 0) {
  $Message = ($DockerVersionOutput | Out-String).Trim()
  throw "Docker is installed but the Docker Engine is not available. Start or restart Docker Desktop, wait until it is running, then retry. Docker output: $Message"
}

$DockerInfoOutput = docker info 2>&1
if ($LASTEXITCODE -ne 0) {
  $Message = ($DockerInfoOutput | Out-String).Trim()
  throw "Docker Engine did not respond correctly. Restart Docker Desktop or switch to Linux containers, then retry. Docker output: $Message"
}

Write-Host "Building backend image: $BackendImage"
Invoke-Docker build -f (Join-Path $DeployDir "backend.Dockerfile") -t $BackendImage $RepoRoot

Write-Host "Building frontend image: $FrontendImage"
Invoke-Docker build -f (Join-Path $DeployDir "frontend.Dockerfile") -t $FrontendImage $RepoRoot

Write-Host "Saving application images"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
Invoke-Docker save -o (Join-Path $OutputDir "ai-code-review-backend-$Version.tar") $BackendImage
Invoke-Docker save -o (Join-Path $OutputDir "ai-code-review-frontend-$Version.tar") $FrontendImage

if ($IncludeMysqlImage) {
  Write-Host "Pulling and saving MySQL image: $MysqlImage"
  Invoke-Docker pull $MysqlImage
  Invoke-Docker save -o (Join-Path $OutputDir "mysql-8.4.tar") $MysqlImage
}

Copy-Item (Join-Path $DeployDir "docker-compose.runtime.yml") (Join-Path $OutputDir "docker-compose.yml")
Copy-Item (Join-Path $DeployDir ".env.example") (Join-Path $OutputDir ".env.example")

$EnvExamplePath = Join-Path $OutputDir ".env.example"
$EnvExample = Get-Content -Raw -Path $EnvExamplePath
$EnvExample = $EnvExample -replace "APP_VERSION=local", "APP_VERSION=$Version"
Set-Content -Path $EnvExamplePath -Value $EnvExample -NoNewline

$LoadScript = @"
#!/usr/bin/env bash
set -euo pipefail

docker load -i ai-code-review-backend-$Version.tar
docker load -i ai-code-review-frontend-$Version.tar

if [ -f mysql-8.4.tar ]; then
  docker load -i mysql-8.4.tar
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example. Edit .env before starting services."
fi

echo "Images loaded. Start with: docker compose up -d"
"@

Set-Content -Path (Join-Path $OutputDir "load-images.sh") -Value $LoadScript -NoNewline

Write-Host ""
Write-Host "Docker deploy package created:"
Write-Host $OutputDir
Write-Host ""
Write-Host "Upload this directory to the Linux server, then run:"
Write-Host "  chmod +x load-images.sh"
Write-Host "  ./load-images.sh"
Write-Host "  vi .env"
Write-Host "  docker compose up -d"
