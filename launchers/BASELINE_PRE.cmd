@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

set "LABEL=pre-%DATE:~-4%%DATE:~4,2%%DATE:~7,2%-%TIME:~0,2%%TIME:~3,2%%TIME:~6,2%"
set "LABEL=%LABEL: =0%"

powershell -NoProfile -ExecutionPolicy Bypass -File ".\baseline.ps1" pre -Label "%LABEL%" -Commit
if errorlevel 1 (
  echo.
  echo PRE failed. Check output above.
  pause
  exit /b 1
)

echo.
echo PRE complete: %LABEL%
pause
