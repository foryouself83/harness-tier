@echo off
setlocal
set "GB=%ProgramFiles%\Git\bin\bash.exe"
"%GB%" "%~dp0probe.sh"
if errorlevel 2 exit /b 0
exit /b %errorlevel%
