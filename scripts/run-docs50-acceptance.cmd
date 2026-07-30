@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-docs50-acceptance.ps1" %*
exit /b %ERRORLEVEL%
