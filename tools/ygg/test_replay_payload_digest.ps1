<#
Level 2 test: replay protection on canonical_payload_digest.

- Uses a temporary canon root under %TEMP%
- Runs two envelopes with different canonical_event_id but identical payload/digest
- Expect: second run denies REPLAY_PAYLOAD_DIGEST

Usage:
  powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\ygg\test_replay_payload_digest.ps1
#>

[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$py = 'C:/Projects/SQUAD/.venv/Scripts/python.exe'
$tmpCanon = Join-Path $env:TEMP ('ygg_canon_test_replay_digest_' + [guid]::NewGuid().ToString('n'))

$envJson1 = .\tools\ygg\emit-event.ps1 -Intent baseline_pre_check -Repo auernyx-agent

# Ensure canonical_event_id changes (emitter uses yyyyMMdd_HHmmss).
$e1 = $envJson1 | ConvertFrom-Json
$tries = 0
do {
  Start-Sleep -Milliseconds 1100
  $envJson2 = .\tools\ygg\emit-event.ps1 -Intent baseline_pre_check -Repo auernyx-agent
  $e2 = $envJson2 | ConvertFrom-Json
  $tries++
  if ($tries -gt 5) { break }
} while ($e1.canonical_event_id -eq $e2.canonical_event_id)

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$tmpEnv1 = Join-Path $env:TEMP ('ygg_env1_' + [guid]::NewGuid().ToString('n') + '.json')
$tmpEnv2 = Join-Path $env:TEMP ('ygg_env2_' + [guid]::NewGuid().ToString('n') + '.json')
[System.IO.File]::WriteAllText($tmpEnv1, $envJson1, $utf8NoBom)
[System.IO.File]::WriteAllText($tmpEnv2, $envJson2, $utf8NoBom)

try {
  $e1 = $envJson1 | ConvertFrom-Json
  $e2 = $envJson2 | ConvertFrom-Json
  if ($e1.canonical_payload_digest -ne $e2.canonical_payload_digest) {
    throw "Test setup failed: payload digests differ. e1=$($e1.canonical_payload_digest) e2=$($e2.canonical_payload_digest)"
  }
  if ($e1.canonical_event_id -eq $e2.canonical_event_id) {
    throw "Test setup failed: event ids are identical."
  }

  $out1 = (& $py .\tools\ygg\auernyx_branch_cli.py --input-file $tmpEnv1 --write-receipt --canon-root $tmpCanon) | ConvertFrom-Json
  if ($out1.decision -eq 'deny') { throw "First run unexpectedly denied: $($out1.reason_codes -join ', ')" }

  $out2 = (& $py .\tools\ygg\auernyx_branch_cli.py --input-file $tmpEnv2 --write-receipt --canon-root $tmpCanon) | ConvertFrom-Json
  if ($out2.decision -ne 'deny') { throw "Expected second run to deny; got $($out2.decision)" }

  $codes2 = @($out2.reason_codes)
  if ($codes2 -notcontains 'REPLAY_PAYLOAD_DIGEST') {
    throw "Expected REPLAY_PAYLOAD_DIGEST; got: $($codes2 -join ', ')"
  }

  Write-Host '[PASS] REPLAY_PAYLOAD_DIGEST enforced.'
} finally {
  foreach ($p in @($tmpEnv1, $tmpEnv2)) {
    if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p -Force -ErrorAction SilentlyContinue }
  }
  if (Test-Path -LiteralPath $tmpCanon) { Remove-Item -LiteralPath $tmpCanon -Recurse -Force -ErrorAction SilentlyContinue }
}
