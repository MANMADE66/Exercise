@echo off
rem One-click stop for the dev servers: kills whatever listens on 8000 / 5173,
rem including child processes. Pure CMD, no Git Bash needed.
rem
rem Usage: double-click, or run `stop.cmd` from CMD/PowerShell.
setlocal enabledelayedexpansion
set "FOUND=0"

for %%P in (8000 5173) do (
  for /f "tokens=2,5" %%A in ('netstat -ano ^| findstr /i "LISTENING" ^| findstr ":%%P "') do (
    set "FOUND=1"
    echo Stopping port %%P  PID %%B  ^(%%A^)
    taskkill /PID %%B /T /F >nul 2>&1
  )
)

if "%FOUND%"=="0" (
  echo Nothing listening on 8000 / 5173 - servers are already stopped.
) else (
  echo.
  echo Stopped. Logs remain in .dev-logs\
)
exit /b 0
