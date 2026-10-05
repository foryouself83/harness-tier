@echo off
setlocal
set "GB="
for /f "delims=" %%G in ('where git 2^>nul') do if not defined GB if exist "%%~dpG..\bin\bash.exe" set "GB=%%~dpG..\bin\bash.exe"
if not defined GB for /f "delims=" %%G in ('where git 2^>nul') do if not defined GB if exist "%%~dpG..\..\bin\bash.exe" set "GB=%%~dpG..\..\bin\bash.exe"
if not defined GB if exist "%ProgramFiles%\Git\bin\bash.exe" set "GB=%ProgramFiles%\Git\bin\bash.exe"
rem Without Git Bash no hook runs; SessionStart's plain stdout is the one channel that reaches
rem the session, so it says the rule is missing rather than leaving it out in silence.
if not defined GB if /i "%~1"=="inject-risk-tiers.sh" echo harness-tier: Git Bash was not found, so the risk-tier rule was not loaded and the commit gate cannot run. Tell the user to install Git for Windows.
if not defined GB exit /b 0
"%GB%" "%~dp0..\%~1" %2 %3
exit /b %errorlevel%
