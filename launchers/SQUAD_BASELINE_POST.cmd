@echo off
setlocal
cd /d "%~dp0\.."
powershell -NoProfile -ExecutionPolicy Bypass -File ".\tools\baseline\baseline.ps1" post -Label "SQUAD-session-end" -ProjectRoot "%CD%" -VerifyHashes -Commit
endlocal
