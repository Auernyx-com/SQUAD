@echo off
setlocal
cd /d "%~dp0\.."
powershell -NoProfile -ExecutionPolicy Bypass -File ".\tools\baseline\baseline.ps1" pre -Label "SQUAD-session-start" -Commit
endlocal
