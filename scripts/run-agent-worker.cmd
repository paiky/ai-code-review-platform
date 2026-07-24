@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-agent-worker.ps1" %*
exit /b %ERRORLEVEL%
