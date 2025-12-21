@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

set "LABEL=post-%DATE:~-4%%DATE:~4,2%%DATE:~7,2%-%TIME:~0,2%%TIME:~3,2%%TIME:~6,2%"
set "LABEL=%LABEL: =0%"

powershell -NoProfile -ExecutionPolicy Bypass -File ".\baseline.ps1" post -Label "%LABEL%" -VerifyHashes -Commit
if errorlevel 1 (
  echo.
  echo POST failed (hash drift or runtime error). Check output above.
  pause
  exit /b 1
)

echo.
echo POST complete: %LABEL%
pause
