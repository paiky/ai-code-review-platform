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

function Write-Utf8NoBomFile {
  param(
    [string]$Path,
    [string]$Content
  )

  $Content = $Content -replace "`r`n", "`n"
  $Content = $Content -replace "`r", "`n"
  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllText($Path, $Content, $utf8NoBom)
}

function Copy-TextFileAsLf {
  param(
    [string]$SourcePath,
    [string]$TargetPath
  )

  $Content = Get-Content -Raw -Encoding UTF8 -Path $SourcePath
  Write-Utf8NoBomFile -Path $TargetPath -Content $Content
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

Copy-TextFileAsLf (Join-Path $DeployDir "docker-compose.runtime.yml") (Join-Path $OutputDir "docker-compose.yml")
Copy-TextFileAsLf (Join-Path $DeployDir ".env.example") (Join-Path $OutputDir ".env.example")

$EnvExamplePath = Join-Path $OutputDir ".env.example"
$EnvExample = Get-Content -Raw -Encoding UTF8 -Path $EnvExamplePath
$EnvExample = $EnvExample -replace "APP_VERSION=local", "APP_VERSION=$Version"
Write-Utf8NoBomFile -Path $EnvExamplePath -Content $EnvExample

$LoadScript = @"
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="`$(cd "`$(dirname "`${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_HOME="`${DEPLOY_HOME:-`$(dirname "`$SCRIPT_DIR")/runtime}"

docker load -i ai-code-review-backend-$Version.tar
docker load -i ai-code-review-frontend-$Version.tar

if [ -f mysql-8.4.tar ]; then
  docker load -i mysql-8.4.tar
fi

mkdir -p "`$DEPLOY_HOME"
cp docker-compose.yml "`$DEPLOY_HOME/docker-compose.yml"

ENV_FILE="`$DEPLOY_HOME/.env"
if [ ! -f "`$ENV_FILE" ]; then
  cp .env.example "`$ENV_FILE"
  echo "Created `$ENV_FILE from .env.example. Edit it once before starting services."
else
  if grep -q '^APP_VERSION=' "`$ENV_FILE"; then
    sed -i 's/^APP_VERSION=.*/APP_VERSION=$Version/' "`$ENV_FILE"
  else
    TMP_ENV="`$(mktemp)"
    {
      echo "APP_VERSION=$Version"
      cat "`$ENV_FILE"
    } > "`$TMP_ENV"
    mv "`$TMP_ENV" "`$ENV_FILE"
  fi
fi

echo "Images loaded. Runtime files are in: `$DEPLOY_HOME"
echo "Start or upgrade with:"
echo "  cd `$DEPLOY_HOME"
echo "  docker compose up -d"
"@

Write-Utf8NoBomFile -Path (Join-Path $OutputDir "load-images.sh") -Content $LoadScript

Write-Host ""
Write-Host "Docker deploy package created:"
Write-Host $OutputDir
Write-Host ""
Write-Host "Upload this directory to the Linux server, then run:"
Write-Host "  chmod +x load-images.sh"
Write-Host "  ./load-images.sh"
Write-Host "  vi ../runtime/.env"
Write-Host "  cd ../runtime"
Write-Host "  docker compose up -d"
