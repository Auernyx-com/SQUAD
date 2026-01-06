<#
Level 2 test: chain tamper detection.

- Uses a temporary canon root under %TEMP%
- Appends one receipt to create HEAD/INDEX
- Mutates HEAD to an incorrect value
- Attempts to append another receipt
- Expect: deny LEDGER_TAMPER_DETECTED

Usage:
  powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\ygg\test_chain_tamper.ps1
#>

[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$py = 'C:/Projects/SQUAD/.venv/Scripts/python.exe'
$tmpCanon = Join-Path $env:TEMP ('ygg_canon_test_chain_tamper_' + [guid]::NewGuid().ToString('n'))

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

$envJson1 = .\tools\ygg\emit-event.ps1 -Intent baseline_pre_check -Repo auernyx-agent
Start-Sleep -Milliseconds 200
$envJson2 = .\tools\ygg\emit-event.ps1 -Intent baseline_pre_check -Repo auernyx-agent -ParamKV mode=run

$tmpEnv1 = Join-Path $env:TEMP ('ygg_env1_' + [guid]::NewGuid().ToString('n') + '.json')
$tmpEnv2 = Join-Path $env:TEMP ('ygg_env2_' + [guid]::NewGuid().ToString('n') + '.json')
[System.IO.File]::WriteAllText($tmpEnv1, $envJson1, $utf8NoBom)
[System.IO.File]::WriteAllText($tmpEnv2, $envJson2, $utf8NoBom)

try {
  $out1 = (& $py .\tools\ygg\auernyx_branch_cli.py --input-file $tmpEnv1 --write-receipt --canon-root $tmpCanon) | ConvertFrom-Json
  if ($out1.decision -eq 'deny') { throw "First run unexpectedly denied: $($out1.reason_codes -join ', ')" }

  $headPath = Join-Path $tmpCanon 'ledger\HEAD'
  if (-not (Test-Path -LiteralPath $headPath)) { throw "HEAD missing at $headPath" }

  # Tamper the head
  'sha256:deadbeef' | Out-File -LiteralPath $headPath -Encoding utf8 -Force

  $out2 = (& $py .\tools\ygg\auernyx_branch_cli.py --input-file $tmpEnv2 --write-receipt --canon-root $tmpCanon) | ConvertFrom-Json
  if ($out2.decision -ne 'deny') { throw "Expected deny after tamper; got $($out2.decision)" }

  $codes2 = @($out2.reason_codes)
  if ($codes2 -notcontains 'LEDGER_TAMPER_DETECTED') {
    throw "Expected LEDGER_TAMPER_DETECTED; got: $($codes2 -join ', ')"
  }

  Write-Host '[PASS] LEDGER_TAMPER_DETECTED enforced.'
} finally {
  foreach ($p in @($tmpEnv1, $tmpEnv2)) {
    if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p -Force -ErrorAction SilentlyContinue }
  }
  if (Test-Path -LiteralPath $tmpCanon) { Remove-Item -LiteralPath $tmpCanon -Recurse -Force -ErrorAction SilentlyContinue }
}
