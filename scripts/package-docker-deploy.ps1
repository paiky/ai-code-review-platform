param(
  [string]$Version = (Get-Date -Format "yyyyMMddHHmmss"),
  [switch]$IncludeMysqlImage,
  [switch]$AgentWorkerOnly,
  [string]$ReuseVersion,
  [switch]$PauseOnError
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
$DeployDir = Join-Path $RepoRoot "deploy"
$OutputDir = Join-Path $RepoRoot ".local\docker-deploy\$Version"
$LogDir = Join-Path $RepoRoot ".local\docker-deploy\logs"
$SafeLogVersion = $Version -replace '[^0-9A-Za-z._-]', '_'
$LogTimestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$LogPath = Join-Path $LogDir "package-$SafeLogVersion-$LogTimestamp-$PID.log"

$BackendImage = "ai-code-review-backend:$Version"
$FrontendImage = "ai-code-review-frontend:$Version"
$AgentWorkerImage = "ai-code-review-agent-worker:$Version"
$AgentEgressImage = "ai-code-review-agent-egress:$Version"
$MysqlImage = "mysql:8.4"

function Test-StartedFromExplorer {
  try {
    $CurrentProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $PID"
    if ($null -eq $CurrentProcess) {
      return $false
    }

    $ParentProcess = Get-Process -Id $CurrentProcess.ParentProcessId -ErrorAction Stop
    return $ParentProcess.ProcessName -eq "explorer"
  } catch {
    return $false
  }
}

function Invoke-Docker {
  $Arguments = $args
  & docker @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "Docker command failed with exit code ${LASTEXITCODE}: docker $($Arguments -join ' ')"
  }
}

function Invoke-DockerProbe {
  param(
    [string[]]$Arguments
  )

  $PreviousErrorActionPreference = $ErrorActionPreference
  try {
    $ErrorActionPreference = "Continue"
    $Output = & docker @Arguments 2>&1
    $ExitCode = $LASTEXITCODE
  } finally {
    $ErrorActionPreference = $PreviousErrorActionPreference
  }

  return @{
    ExitCode = $ExitCode
    Output = (($Output | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine).Trim()
  }
}

function Use-ReusedDockerImage {
  param(
    [string]$Component,
    [string]$SourceImage,
    [string]$TargetImage
  )

  $Probe = Invoke-DockerProbe -Arguments @(
    "image",
    "inspect",
    "--format",
    "{{.Id}}",
    $SourceImage
  )
  if ($Probe.ExitCode -ne 0) {
    throw "Agent Worker incremental package requires local $Component image '$SourceImage'. Build or load that complete version first."
  }

  Write-Host "Reusing $Component image: $SourceImage -> $TargetImage"
  Invoke-Docker tag $SourceImage $TargetImage
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

$TranscriptStarted = $false
$Failure = $null
$ShouldPauseOnError = -not $env:NO_PAUSE -and ($PauseOnError -or (Test-StartedFromExplorer))

try {
  New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
  Start-Transcript -Path $LogPath -Force | Out-Null
  $TranscriptStarted = $true

  Write-Host "Docker deploy package log:"
  Write-Host $LogPath
  Write-Host ""

  if ($Version -notmatch '^[0-9A-Za-z._-]+$') {
    throw "Version may only contain letters, numbers, dot, underscore, and hyphen."
  }
  if ($AgentWorkerOnly) {
    if ([string]::IsNullOrWhiteSpace($ReuseVersion)) {
      throw "-AgentWorkerOnly requires -ReuseVersion with a previously completed local image version."
    }
    if ($ReuseVersion -notmatch '^[0-9A-Za-z._-]+$') {
      throw "ReuseVersion may only contain letters, numbers, dot, underscore, and hyphen."
    }
    if ($ReuseVersion -eq $Version) {
      throw "ReuseVersion must differ from the new Version."
    }
  } elseif (-not [string]::IsNullOrWhiteSpace($ReuseVersion)) {
    throw "-ReuseVersion is only valid together with -AgentWorkerOnly."
  }

  if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker command was not found. Install Docker Desktop, start it, then reopen PowerShell or Cursor before running this script."
  }

  $DockerVersionProbe = Invoke-DockerProbe version
  if ($DockerVersionProbe.ExitCode -ne 0) {
    throw "Docker is installed but the Docker Engine is not available. Start or restart Docker Desktop, wait until it is running, then retry. Docker output: $($DockerVersionProbe.Output)"
  }

  $DockerInfoProbe = Invoke-DockerProbe info
  if ($DockerInfoProbe.ExitCode -ne 0) {
    throw "Docker Engine did not respond correctly. Restart Docker Desktop or switch to Linux containers, then retry. Docker output: $($DockerInfoProbe.Output)"
  }

  if ($AgentWorkerOnly) {
    Use-ReusedDockerImage `
      -Component "backend" `
      -SourceImage "ai-code-review-backend:$ReuseVersion" `
      -TargetImage $BackendImage
    Use-ReusedDockerImage `
      -Component "frontend" `
      -SourceImage "ai-code-review-frontend:$ReuseVersion" `
      -TargetImage $FrontendImage
    Use-ReusedDockerImage `
      -Component "Agent egress proxy" `
      -SourceImage "ai-code-review-agent-egress:$ReuseVersion" `
      -TargetImage $AgentEgressImage
  } else {
    Write-Host "Building backend image: $BackendImage"
    Invoke-Docker build -f (Join-Path $DeployDir "backend.Dockerfile") -t $BackendImage $RepoRoot

    Write-Host "Building frontend image: $FrontendImage"
    Invoke-Docker build -f (Join-Path $DeployDir "frontend.Dockerfile") -t $FrontendImage $RepoRoot
  }

  Write-Host "Building Agent Worker image: $AgentWorkerImage"
  Invoke-Docker build -f (Join-Path $DeployDir "agent-review-worker.Dockerfile") -t $AgentWorkerImage $RepoRoot

  if (-not $AgentWorkerOnly) {
    Write-Host "Building Agent egress proxy image: $AgentEgressImage"
    Invoke-Docker build -f (Join-Path $DeployDir "agent-egress-proxy.Dockerfile") -t $AgentEgressImage $RepoRoot
  }

  Write-Host "Saving application images"
  New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
  Invoke-Docker save -o (Join-Path $OutputDir "ai-code-review-backend-$Version.tar") $BackendImage
  Invoke-Docker save -o (Join-Path $OutputDir "ai-code-review-frontend-$Version.tar") $FrontendImage
  Invoke-Docker save -o (Join-Path $OutputDir "ai-code-review-agent-worker-$Version.tar") $AgentWorkerImage
  Invoke-Docker save -o (Join-Path $OutputDir "ai-code-review-agent-egress-$Version.tar") $AgentEgressImage

  if ($IncludeMysqlImage) {
    Write-Host "Pulling and saving MySQL image: $MysqlImage"
    Invoke-Docker pull $MysqlImage
    Invoke-Docker save -o (Join-Path $OutputDir "mysql-8.4.tar") $MysqlImage
  }

  Copy-TextFileAsLf (Join-Path $DeployDir "docker-compose.runtime.yml") (Join-Path $OutputDir "docker-compose.yml")
  Copy-TextFileAsLf (Join-Path $DeployDir ".env.example") (Join-Path $OutputDir ".env.example")
  Copy-TextFileAsLf (Join-Path $DeployDir "deploy-stage3.sh") (Join-Path $OutputDir "deploy-stage3.sh")

  $EnvExamplePath = Join-Path $OutputDir ".env.example"
  $EnvExample = Get-Content -Raw -Encoding UTF8 -Path $EnvExamplePath
  $EnvExample = $EnvExample -replace "APP_VERSION=local", "APP_VERSION=$Version"
  Write-Utf8NoBomFile -Path $EnvExamplePath -Content $EnvExample

  $LoadScript = @"
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="`$(cd "`$(dirname "`${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_HOME="`${DEPLOY_HOME:-`$(dirname "`$SCRIPT_DIR")/runtime}"
KEEP_IMAGE_VERSIONS="`${KEEP_IMAGE_VERSIONS:-2}"

cleanup_old_images() {
  local repo="`$1"
  local keep_count="`$2"

  if ! [[ "`$keep_count" =~ ^[0-9]+$ ]]; then
    echo "Skip image cleanup for `$repo: KEEP_IMAGE_VERSIONS is not a non-negative integer: `$keep_count"
    return 0
  fi

  mapfile -t tags < <(docker image ls "`$repo" --format '{{.Tag}}' | grep -E '^[0-9]{14}$' | awk '!seen[`$0]++' | sort -r)
  if [ "`${#tags[@]}" -le "`$keep_count" ]; then
    return 0
  fi

  for tag in "`${tags[@]:`$keep_count}"; do
    if docker image rm "`$repo:`$tag" >/dev/null 2>&1; then
      echo "Removed old image: `$repo:`$tag"
    else
      echo "Skipped removing old image still in use: `$repo:`$tag"
    fi
  done
}

docker load -i ai-code-review-backend-$Version.tar
docker load -i ai-code-review-frontend-$Version.tar
docker load -i ai-code-review-agent-worker-$Version.tar
docker load -i ai-code-review-agent-egress-$Version.tar

if [ -f mysql-8.4.tar ]; then
  docker load -i mysql-8.4.tar
fi

mkdir -p "`$DEPLOY_HOME"
cp docker-compose.yml "`$DEPLOY_HOME/docker-compose.yml"
cp "`$SCRIPT_DIR/deploy-stage3.sh" "`$DEPLOY_HOME/deploy-stage3.sh"
chmod +x "`$DEPLOY_HOME/deploy-stage3.sh"

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

cleanup_old_images "ai-code-review-backend" "`$KEEP_IMAGE_VERSIONS"
cleanup_old_images "ai-code-review-frontend" "`$KEEP_IMAGE_VERSIONS"
cleanup_old_images "ai-code-review-agent-worker" "`$KEEP_IMAGE_VERSIONS"
cleanup_old_images "ai-code-review-agent-egress" "`$KEEP_IMAGE_VERSIONS"

echo "Images loaded. Runtime files are in: `$DEPLOY_HOME"
echo "Safe Stage 3 upgrade:"
echo "  cd `$DEPLOY_HOME"
echo "  ./deploy-stage3.sh upgrade --workers 2"
echo "Direct Compose remains available for recovery:"
echo "  docker compose --env-file .env -f docker-compose.yml up -d"
echo "Image retention:"
echo "  KEEP_IMAGE_VERSIONS=`$KEEP_IMAGE_VERSIONS"
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
  Write-Host "  ./deploy-stage3.sh upgrade --workers 2"
} catch {
  $Failure = $_
  Write-Host ""
  Write-Host "Docker deploy package failed." -ForegroundColor Red
  Write-Host $_.Exception.Message -ForegroundColor Red
  Write-Host ""
  Write-Host "PowerShell error details:"
  Write-Host ($_ | Format-List * -Force | Out-String)
} finally {
  if ($TranscriptStarted) {
    try {
      Stop-Transcript | Out-Null
    } catch {
      Write-Warning "Could not close Docker deploy package log: $($_.Exception.Message)"
    }
  }
}

if ($null -ne $Failure) {
  Write-Host "Full build log:"
  Write-Host $LogPath
  if ($ShouldPauseOnError) {
    Read-Host "Press Enter to close this window" | Out-Null
  }
  exit 1
}

Write-Host ""
Write-Host "Full build log:"
Write-Host $LogPath
