$ErrorActionPreference = "Stop"

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Push-Location $repositoryRoot

try {
    if (-not (Get-Command codegraph -ErrorAction SilentlyContinue)) {
        Write-Host "[setup-codegraph] codegraph not found, installing @colbymchenry/codegraph globally..."
        & npm install -g @colbymchenry/codegraph
        if ($LASTEXITCODE -ne 0) {
            throw "[setup-codegraph] failed to install codegraph"
        }
    }

    if (-not (Test-Path -LiteralPath ".cursor/mcp.json" -PathType Leaf)) {
        throw "[setup-codegraph] missing version-controlled .cursor/mcp.json"
    }

    if (-not (Test-Path -LiteralPath ".codegraph/codegraph.db" -PathType Leaf)) {
        Write-Host "[setup-codegraph] building initial index..."
        & codegraph init -i
        if ($LASTEXITCODE -ne 0) {
            throw "[setup-codegraph] failed to build index"
        }
    }
    else {
        Write-Host "[setup-codegraph] index already exists, syncing..."
        & codegraph sync
        if ($LASTEXITCODE -ne 0) {
            throw "[setup-codegraph] failed to sync index"
        }
    }

    & codegraph status
    if ($LASTEXITCODE -ne 0) {
        throw "[setup-codegraph] failed to read index status"
    }

    Write-Host ""
    Write-Host "[setup-codegraph] done. Restart Cursor to load the project MCP server."
}
finally {
    Pop-Location
}
