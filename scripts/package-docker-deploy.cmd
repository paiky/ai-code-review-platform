@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0package-docker-deploy.ps1" %*
set EXIT_CODE=%ERRORLEVEL%
if not "%EXIT_CODE%"=="0" (
  echo.
  echo Docker deploy package failed with exit code %EXIT_CODE%.
  echo Review the error output above.
  if not defined NO_PAUSE pause
)
exit /b %EXIT_CODE%
