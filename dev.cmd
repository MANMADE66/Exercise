@echo off
rem One-click dev launcher (Windows wrapper around scripts/dev.sh).
rem
rem Why this exists: in CMD/PowerShell the command `bash` resolves to
rem C:\Windows\System32\bash.exe, the WSL launcher, which fails with
rem "no installed distributions" when WSL is absent. This script locates
rem Git's own bash.exe instead and never touches WSL.
rem
rem Usage: double-click, or run `dev.cmd` from CMD/PowerShell.
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "BASH="
for /f "delims=" %%G in ('where git 2^>nul') do (
  call :probe "%%~dpG..\..\bin\bash.exe"
  call :probe "%%~dpG..\bin\bash.exe"
)
if not defined BASH call :probe "C:\Program Files\Git\bin\bash.exe"
if not defined BASH call :probe "C:\Program Files (x86)\Git\bin\bash.exe"
if not defined BASH call :probe "D:\Git\bin\bash.exe"

if not defined BASH (
  echo.
  echo [x] Git Bash not found ^(bash.exe^).
  echo     Install Git for Windows: https://git-scm.com/download/win
  echo     Or start the two processes by hand in two PowerShell windows:
  echo       cd backend  ^&^&  uv run uvicorn app.main:app --reload --port 8000
  echo       cd frontend ^&^&  npm run dev
  echo.
  pause
  exit /b 1
)

echo Using Git Bash: %BASH%
echo.
"%BASH%" scripts/dev.sh %*
exit /b %errorlevel%

:probe
if not defined BASH if exist %1 set "BASH=%~1"
exit /b 0
