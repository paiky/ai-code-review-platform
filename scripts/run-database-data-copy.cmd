@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-database-data-copy.ps1" %*
exit /b %ERRORLEVEL%
