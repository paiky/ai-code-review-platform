@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0init-agent-review-secrets.ps1" %*
exit /b %ERRORLEVEL%
