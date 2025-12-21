@echo off
setlocal
cd /d "%~dp0\.."
set "LEDGER=C:\baseline-algorithms-and-programs"
powershell -NoProfile -ExecutionPolicy Bypass -File ".\tools\baseline\baseline.ps1" pre -Label "SQUAD-session-start" -ProjectRoot "%CD%" -LedgerRoot "%LEDGER%" -Commit
endlocal
