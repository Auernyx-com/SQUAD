<#
Negative test: DIGEST_MISMATCH must be detected.

- Emits a valid envelope
- Mutates canonical_payload without updating canonical_payload_digest
- Invokes local branch agent CLI
- Asserts decision=deny and reason_codes contains DIGEST_MISMATCH

Usage:
  powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\ygg\test_digest_mismatch.ps1
#>

[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$py = 'C:/Projects/SQUAD/.venv/Scripts/python.exe'

$envJson = .\tools\ygg\emit-event.ps1 -Intent baseline_pre_check -Repo auernyx-agent
$envObj = $envJson | ConvertFrom-Json

# Mutate payload but keep digest the same (intentional mismatch)
$envObj.canonical_payload.parameters.mode = 'run'

$tmp = Join-Path $env:TEMP ('ygg_mismatch_' + [guid]::NewGuid().ToString('n') + '.json')
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($tmp, ($envObj | ConvertTo-Json -Depth 100 -Compress), $utf8NoBom)

try {
  $outJson = & $py .\tools\ygg\auernyx_branch_cli.py --input-file $tmp
  $out = $outJson | ConvertFrom-Json

  if ($out.decision -ne 'deny') {
    Write-Error ("Expected decision=deny, got: {0}" -f $out.decision)
    exit 1
  }

  $codes = @($out.reason_codes)
  $ok = ($codes -contains 'DIGEST_MISMATCH') -or ($codes -contains 'CANONICAL_PAYLOAD_OBJECT_MISMATCH')
  if (-not $ok) {
    Write-Error ("Expected reason_codes to include DIGEST_MISMATCH or CANONICAL_PAYLOAD_OBJECT_MISMATCH. Got: {0}" -f ($codes -join ', '))
    exit 1
  }

  Write-Host '[PASS] Tamper detected as expected.'
  exit 0
} finally {
  if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }
}
