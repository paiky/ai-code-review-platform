@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0verify-gitlab-diff.ps1" %*
set EXIT_CODE=%ERRORLEVEL%
if not "%EXIT_CODE%"=="0" (
  echo.
  echo GitLab validation failed with exit code %EXIT_CODE%.
  echo Review the error output above.
  if not defined NO_PAUSE pause
)
exit /b %EXIT_CODE%
