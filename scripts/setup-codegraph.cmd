@echo off
setlocal

cd /d "%~dp0.."

where codegraph >nul 2>&1
if errorlevel 1 (
  echo [setup-codegraph] codegraph not found, installing @colbymchenry/codegraph globally...
  call npm install -g @colbymchenry/codegraph
  if errorlevel 1 (
    echo [setup-codegraph] failed to install codegraph
    exit /b 1
  )
)

if not exist ".cursor\mcp.json" (
  echo [setup-codegraph] missing version-controlled .cursor\mcp.json
  exit /b 1
)

if not exist ".codegraph\codegraph.db" (
  echo [setup-codegraph] building initial index...
  call codegraph init -i
  if errorlevel 1 (
    echo [setup-codegraph] failed to build index
    exit /b 1
  )
) else (
  echo [setup-codegraph] index already exists, syncing...
  call codegraph sync
)

call codegraph status
echo.
echo [setup-codegraph] done. Restart Cursor to load the project MCP server.

endlocal
