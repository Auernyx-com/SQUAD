@echo off
setlocal
cd /d "%~dp0\.."
set "LEDGER=C:\baseline-algorithms-and-programs"
powershell -NoProfile -ExecutionPolicy Bypass -File ".\tools\baseline\baseline.ps1" post -Label "SQUAD-session-end" -ProjectRoot "%CD%" -LedgerRoot "%LEDGER%" -VerifyHashes -Commit
endlocal
