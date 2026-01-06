<#
Level 2 test: replay protection on canonical_event_id.

- Uses a temporary canon root under %TEMP% (no repo pollution)
- Runs the same envelope twice
- Expect: first run advances chain, second run denies REPLAY_EVENT_ID

Usage:
  powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\ygg\test_replay_event_id.ps1
#>

[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$py = 'C:/Projects/SQUAD/.venv/Scripts/python.exe'
$tmpCanon = Join-Path $env:TEMP ('ygg_canon_test_replay_event_' + [guid]::NewGuid().ToString('n'))

$envJson = .\tools\ygg\emit-event.ps1 -Intent baseline_pre_check -Repo auernyx-agent
$tmpEnv = Join-Path $env:TEMP ('ygg_env_' + [guid]::NewGuid().ToString('n') + '.json')
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($tmpEnv, $envJson, $utf8NoBom)

try {
  $out1 = (& $py .\tools\ygg\auernyx_branch_cli.py --input-file $tmpEnv --write-receipt --canon-root $tmpCanon) | ConvertFrom-Json
  if ($out1.decision -eq 'deny') { throw "First run unexpectedly denied: $($out1.reason_codes -join ', ')" }

  $out2 = (& $py .\tools\ygg\auernyx_branch_cli.py --input-file $tmpEnv --write-receipt --canon-root $tmpCanon) | ConvertFrom-Json
  if ($out2.decision -ne 'deny') { throw "Expected second run to deny; got $($out2.decision)" }

  $codes2 = @($out2.reason_codes)
  if ($codes2 -notcontains 'REPLAY_EVENT_ID') {
    throw "Expected REPLAY_EVENT_ID; got: $($codes2 -join ', ')"
  }

  Write-Host '[PASS] REPLAY_EVENT_ID enforced.'
} finally {
  if (Test-Path -LiteralPath $tmpEnv) { Remove-Item -LiteralPath $tmpEnv -Force -ErrorAction SilentlyContinue }
  if (Test-Path -LiteralPath $tmpCanon) { Remove-Item -LiteralPath $tmpCanon -Recurse -Force -ErrorAction SilentlyContinue }
}
