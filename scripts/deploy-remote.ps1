[CmdletBinding()]
param(
  [string]$Server,
  [ValidateRange(1, 65535)][int]$Port = 22,
  [string]$User,
  [string]$DeployRoot,
  [string]$PrivateKeyPath,
  [string]$HostKeyFingerprint,
  [ValidateRange(1, 100)][int]$Workers = 2,
  [string]$Ssh2ModulePath
)

$MissingParameters = @('Server', 'User', 'DeployRoot', 'PrivateKeyPath', 'HostKeyFingerprint') |
  Where-Object { [string]::IsNullOrWhiteSpace($PSBoundParameters[$_]) }
if ($MissingParameters) {
  throw "Missing deployment parameters: $($MissingParameters -join ', '). To use the saved local settings, double-click scripts\deploy-remote-double-click.cmd."
}

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$PackageRoot = Join-Path $RepoRoot ".local\docker-deploy"
$PackageScript = Join-Path $PSScriptRoot "package-docker-deploy.ps1"
$RemoteClient = Join-Path $RepoRoot "deploy\remote-deploy-client.cjs"
$Version = Get-Date -Format "yyyyMMddHHmmss"
$PackageDir = Join-Path $PackageRoot $Version
$LogDir = Join-Path $PackageRoot "logs"
$LogPath = Join-Path $LogDir "remote-$Version.log"

function Invoke-RemoteClient {
  param([string]$Mode)

  $ConfigJson = $Config | ConvertTo-Json -Compress
  # Keep the JSON intact across Windows PowerShell's native stdin encoding.
  $AsciiJson = [regex]::Replace($ConfigJson, '[^\x00-\x7F]', {
    param($Character)
    '\u{0:x4}' -f [int][char]$Character.Value
  })
  $AsciiJson | & node $RemoteClient $Mode |
    Tee-Object -FilePath $LogPath -Append | Out-Host
  if ($LASTEXITCODE -ne 0) {
    throw "Remote client exited with code $LASTEXITCODE. See the remote deployment log."
  }
}

$Stage = "Local setup"
try {
  if (-not (Get-Command node -CommandType Application -ErrorAction SilentlyContinue)) {
    throw "Node.js is required. Install it and reopen PowerShell."
  }
  if (-not $Ssh2ModulePath) {
    $Ssh2ModulePath = Join-Path $PackageRoot "ssh\node_modules\ssh2"
  }
  if (-not (Test-Path -LiteralPath $Ssh2ModulePath -PathType Container)) {
    throw "ssh2 was not found. Run 'npm.cmd install --prefix .local/docker-deploy/ssh --no-save --no-package-lock ssh2@1.17.0' from the repository root or pass -Ssh2ModulePath."
  }
  if (-not (Test-Path -LiteralPath $PrivateKeyPath -PathType Leaf)) {
    throw "SSH private key file was not found. Check -PrivateKeyPath."
  }
  if (Test-Path -LiteralPath $PackageDir) {
    throw "Local package directory already exists for version $Version. Start again with a new timestamp."
  }

  New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
  New-Item -ItemType File -Path $LogPath | Out-Null
  $Config = @{
    host = $Server
    port = $Port
    username = $User
    deployRoot = $DeployRoot
    privateKeyPath = (Resolve-Path -LiteralPath $PrivateKeyPath).ProviderPath
    fingerprint = $HostKeyFingerprint
    workers = $Workers
    ssh2ModulePath = (Resolve-Path -LiteralPath $Ssh2ModulePath).ProviderPath
    version = $Version
    packageDir = $PackageDir
  }

  Write-Host "Deploying version $Version to ${User}@${Server}:${Port}"
  $Stage = "Remote preflight"
  Invoke-RemoteClient -Mode "preflight"

  $Stage = "Local package build"
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $PackageScript -Version $Version
  if ($LASTEXITCODE -ne 0) {
    throw "Docker package build exited with code $LASTEXITCODE. See the packaging log printed above."
  }

  $Stage = "Upload and remote upgrade"
  Invoke-RemoteClient -Mode "deploy"
  Write-Host "Deployment completed for version $Version. Log: $LogPath"
} catch {
  Write-Host "Deployment failed at '$Stage' for version ${Version}: $($_.Exception.Message)" -ForegroundColor Red
  if (Test-Path -LiteralPath $LogPath -PathType Leaf) {
    Write-Host "Deployment log: $LogPath"
  }
  exit 1
}
