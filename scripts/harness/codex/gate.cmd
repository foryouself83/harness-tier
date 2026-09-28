@echo off
setlocal
set "GB="
for /f "delims=" %%G in ('where git 2^>nul') do if not defined GB if exist "%%~dpG..\bin\bash.exe" set "GB=%%~dpG..\bin\bash.exe"
if not defined GB if exist "%ProgramFiles%\Git\bin\bash.exe" set "GB=%ProgramFiles%\Git\bin\bash.exe"
if defined GB "%GB%" "%~dp0gate.sh"
if defined GB exit /b %errorlevel%
findstr /i /c:"commit" /c:"merge" >nul || exit /b 0
echo {"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"harness-tier: the commit gate needs Git Bash - install Git for Windows, then retry."}}
exit /b 0
