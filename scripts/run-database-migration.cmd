@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-database-migration.ps1" %*
exit /b %ERRORLEVEL%
