@echo off
setlocal
set "GB="
for /f "delims=" %%G in ('where git 2^>nul') do if not defined GB if exist "%%~dpG..\bin\bash.exe" set "GB=%%~dpG..\bin\bash.exe"
if not defined GB for /f "delims=" %%G in ('where git 2^>nul') do if not defined GB if exist "%%~dpG..\..\bin\bash.exe" set "GB=%%~dpG..\..\bin\bash.exe"
if not defined GB if exist "%ProgramFiles%\Git\bin\bash.exe" set "GB=%ProgramFiles%\Git\bin\bash.exe"
if not defined GB exit /b 0
"%GB%" "%~dp0..\%~1" %2 %3
exit /b %errorlevel%
