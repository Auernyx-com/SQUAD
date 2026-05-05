[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

# ── Root resolution ────────────────────────────────────────────────────────────

function Get-SquadBatRoot {
  $here = (Resolve-Path -LiteralPath $PSScriptRoot).Path
  return (Resolve-Path -LiteralPath (Join-Path $here '..\..\..') ).Path
}

function Get-SquadBatHeadSha([string]$Root) {
  try { return (git -C $Root rev-parse HEAD 2>$null).Trim() } catch { return '' }
}

function Get-IsoTimestampUtc {
  return (Get-Date).ToUniversalTime().ToString('o')
}

function Limit-Text([string]$Text, [int]$MaxChars = 20000) {
  if ($null -eq $Text) { return '' }
  if ($Text.Length -le $MaxChars) { return $Text }
  return $Text.Substring(0, $MaxChars) + "`n...<truncated>..."
}

# ── Founding law verification ──────────────────────────────────────────────────
# No Division runs if the founding law has been tampered with.

$FOUNDING_LAW_LOCKED_SHA256 = 'dc0fcb428e24948c5471798bf3c0b77cafade1c68e1aecb39aa13eef264f2f87'

function Assert-FoundingLaw([string]$Root) {
  $lawPath = Join-Path $Root 'GOVERNANCE\LAWS\veteran_data_sovereignty.v1.md'

  if (-not (Test-Path -LiteralPath $lawPath)) {
    throw "FOUNDING_LAW_MISSING: veteran_data_sovereignty.v1.md not found. Cannot proceed."
  }

  $actual = (Get-FileHash -LiteralPath $lawPath -Algorithm SHA256).Hash.ToLowerInvariant()

  if ($actual -ne $FOUNDING_LAW_LOCKED_SHA256) {
    throw ("FOUNDING_LAW_TAMPERED: hash mismatch.`n  locked:   {0}`n  actual:   {1}`nAll Division operations are suspended until the founding law is restored." -f $FOUNDING_LAW_LOCKED_SHA256, $actual)
  }

  return $actual
}

# ── Config resolution ──────────────────────────────────────────────────────────

function Read-DivisionsConfig([string]$Root) {
  $cfgPath = Join-Path $Root 'config\divisions.json'
  if (-not (Test-Path -LiteralPath $cfgPath)) {
    throw "Missing divisions config: $cfgPath"
  }
  return (Get-Content -LiteralPath $cfgPath -Raw | ConvertFrom-Json)
}

function Resolve-DivisionConfig([string]$Root, [string]$DivisionName) {
  $cfg = Read-DivisionsConfig -Root $Root
  if (-not $cfg.divisions) { throw 'Invalid divisions.json: missing divisions object' }
  $div = $cfg.divisions.$DivisionName
  if ($null -eq $div) { throw "Division not found in config/divisions.json: $DivisionName" }

  $entry = if ($div.PSObject.Properties.Name -contains 'entry') { [string]$div.entry } else { '' }
  $type  = if ($div.PSObject.Properties.Name -contains 'type')  { [string]$div.type  } else { '' }
  $notes = if ($div.PSObject.Properties.Name -contains 'notes') { [string]$div.notes } else { '' }

  return [pscustomobject]@{ name = $DivisionName; entry = $entry; type = $type; notes = $notes }
}

function Resolve-DivisionEntry([string]$Entry) {
  if ([string]::IsNullOrWhiteSpace($Entry)) { return '' }
  return (Resolve-Path -LiteralPath $Entry).Path
}

function Get-EntrySha256([string]$EntryPath) {
  if ([string]::IsNullOrWhiteSpace($EntryPath)) { return '' }
  if (-not (Test-Path -LiteralPath $EntryPath)) { return '' }
  return (Get-FileHash -LiteralPath $EntryPath -Algorithm SHA256).Hash.ToLowerInvariant()
}

# ── Baseline hooks (mirrors BranchInvoke pattern) ─────────────────────────────

function Find-BaselineScript([string]$Root) {
  $candidates = @($env:SQUAD_BAT_BASELINE_SCRIPT, $env:AUERNYX_BASELINE_SCRIPT) |
    Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
  foreach ($c in $candidates) {
    if (Test-Path -LiteralPath $c) { return (Resolve-Path -LiteralPath $c).Path }
  }
  $sibling = Join-Path (Split-Path -Parent $Root) '_baseline_repo_work\baseline.ps1'
  if (Test-Path -LiteralPath $sibling) { return (Resolve-Path -LiteralPath $sibling).Path }
  return ''
}

function Invoke-BaselinePhase {
  param(
    [Parameter(Mandatory)] [ValidateSet('pre','post','verify')] [string]$Mode,
    [Parameter(Mandatory)] [string]$Root,
    [Parameter(Mandatory)] [string]$Label
  )
  $script = Find-BaselineScript -Root $Root
  if ([string]::IsNullOrWhiteSpace($script)) {
    return [pscustomobject]@{ enabled = $false; script = ''; mode = $Mode; label = $Label; stdout = ''; bundleDir = '' }
  }

  $out = Join-Path $Root ('artifacts\receipts\_baseline_{0}_{1}.out.txt' -f $Mode, ([Guid]::NewGuid().ToString('n')))
  $err = Join-Path $Root ('artifacts\receipts\_baseline_{0}_{1}.err.txt' -f $Mode, ([Guid]::NewGuid().ToString('n')))
  New-Item -ItemType Directory -Path (Split-Path -Parent $out) -Force | Out-Null

  $p = Start-Process -FilePath 'powershell' -ArgumentList @(
      '-NoProfile','-ExecutionPolicy','Bypass','-File',$script,$Mode,'-Label',$Label,'-LedgerRoot',$Root
    ) -WorkingDirectory (Split-Path -Parent $script) -Wait -PassThru -NoNewWindow `
      -RedirectStandardOutput $out -RedirectStandardError $err

  $stdout = ''
  if (Test-Path -LiteralPath $out) { $stdout = Get-Content -LiteralPath $out -Raw }
  if (Test-Path -LiteralPath $err) {
    $stderr = Get-Content -LiteralPath $err -Raw
    if (-not [string]::IsNullOrWhiteSpace($stderr)) { $stdout = $stdout + "`n" + $stderr }
  }

  $bundle = ''
  $m = [regex]::Match($stdout, 'State capture bundle created:\s*(.+)$', [System.Text.RegularExpressions.RegexOptions]::Multiline)
  if ($m.Success) { $bundle = $m.Groups[1].Value.Trim() }

  return [pscustomobject]@{
    enabled = $true; script = $script; mode = $Mode; label = $Label
    stdout = (Limit-Text -Text $stdout); bundleDir = $bundle; exitCode = $p.ExitCode
  }
}

# ── Division execution ─────────────────────────────────────────────────────────

function Invoke-ExternalDivision {
  param(
    [Parameter(Mandatory)] [string]$EntryPath,
    [string]$Type = 'auto',
    [string[]]$EntryArgs = @()
  )
  $resolved = (Resolve-Path -LiteralPath $EntryPath).Path
  $workDir  = Split-Path -Parent $resolved
  $ext      = [IO.Path]::GetExtension($resolved).ToLowerInvariant()
  $kind     = $Type

  if ($kind -eq 'auto' -or [string]::IsNullOrWhiteSpace($kind)) {
    if ($ext -eq '.ps1')             { $kind = 'powershell' }
    elseif ($ext -eq '.py')          { $kind = 'python' }
    elseif ($ext -in @('.cmd','.bat')) { $kind = 'cmd' }
    else                             { $kind = 'powershell' }
  }

  $stdoutPath = Join-Path $env:TEMP ('divisioninvoke-{0}-out.txt' -f ([Guid]::NewGuid().ToString('n')))
  $stderrPath = Join-Path $env:TEMP ('divisioninvoke-{0}-err.txt' -f ([Guid]::NewGuid().ToString('n')))

  if ($kind -eq 'python') {
    $proc = Start-Process -FilePath 'python' -ArgumentList (@($resolved) + $EntryArgs) `
      -WorkingDirectory $workDir -Wait -PassThru -NoNewWindow `
      -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
  } elseif ($kind -eq 'cmd') {
    $proc = Start-Process -FilePath 'cmd.exe' -ArgumentList (@('/c',$resolved) + $EntryArgs) `
      -WorkingDirectory $workDir -Wait -PassThru -NoNewWindow `
      -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
  } else {
    $argList = @('-NoProfile','-ExecutionPolicy','Bypass','-File',$resolved) + $EntryArgs
    $proc = Start-Process -FilePath 'powershell' -ArgumentList $argList `
      -WorkingDirectory $workDir -Wait -PassThru -NoNewWindow `
      -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
  }

  $outText = if (Test-Path -LiteralPath $stdoutPath) { Get-Content -LiteralPath $stdoutPath -Raw } else { '' }
  $errText = if (Test-Path -LiteralPath $stderrPath) { Get-Content -LiteralPath $stderrPath -Raw } else { '' }

  return [pscustomobject]@{
    exitCode = $proc.ExitCode
    stdout   = (Limit-Text -Text $outText)
    stderr   = (Limit-Text -Text $errText)
    kind     = $kind
    workDir  = $workDir
  }
}

# ── Ygg ledger receipt ─────────────────────────────────────────────────────────
# Emits a canonical event and appends it to the hash-chain ledger.
# Records outcome only — no PII, no veteran data. Law: veteran_data_sovereignty.v1

function Invoke-YggReceipt {
  param(
    [Parameter(Mandatory)] [string]$Root,
    [Parameter(Mandatory)] [string]$DivisionName,
    [Parameter(Mandatory)] [int]$ExitCode,
    [Parameter(Mandatory)] [string]$Timestamp
  )

  $emitter  = Join-Path $Root 'tools\ygg\emit-event.ps1'
  $cli      = Join-Path $Root 'tools\ygg\auernyx_branch_cli.py'
  $canonDir = Join-Path $Root 'canon'

  if (-not (Test-Path -LiteralPath $emitter) -or -not (Test-Path -LiteralPath $cli)) {
    return [pscustomobject]@{ enabled = $false; reason = 'ygg_tools_not_found' }
  }

  $outcome = if ($ExitCode -eq 0) { 'success' } else { "exit_$ExitCode" }

  $envelopeJson = & powershell -NoProfile -ExecutionPolicy Bypass -File $emitter `
    -Intent "division_invoked" `
    -Repo   "squad-battalion" `
    -Mode   "run" `
    -BranchId "squad-bat.$DivisionName" `
    -ParamKV @("division=$DivisionName","outcome=$outcome","ts=$Timestamp") `
    2>$null

  if ([string]::IsNullOrWhiteSpace($envelopeJson)) {
    return [pscustomobject]@{ enabled = $true; reason = 'emit_failed'; ledger = $null }
  }

  $tmp = Join-Path $env:TEMP ('ygg-envelope-{0}.json' -f [Guid]::NewGuid().ToString('n'))
  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllText($tmp, $envelopeJson, $utf8NoBom)

  try {
    $ledgerOut = & python $cli --input-file $tmp --write-receipt --canon-root $canonDir 2>&1
    $ledgerResult = $ledgerOut | ConvertFrom-Json -ErrorAction SilentlyContinue
    return [pscustomobject]@{ enabled = $true; reason = 'ok'; ledger = $ledgerResult }
  } catch {
    return [pscustomobject]@{ enabled = $true; reason = "ledger_error: $_"; ledger = $null }
  } finally {
    if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }
  }
}

# ── Receipt file ───────────────────────────────────────────────────────────────

function Write-DivisionReceipt {
  param(
    [Parameter(Mandatory)] [string]$Root,
    [Parameter(Mandatory)] [string]$DivisionName,
    [Parameter(Mandatory)] [hashtable]$Receipt
  )
  $dir  = Join-Path $Root 'artifacts\receipts\divisions'
  New-Item -ItemType Directory -Path $dir -Force | Out-Null

  $stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
  $path  = Join-Path $dir ("{0}-{1}.json" -f $stamp, $DivisionName)

  Set-Content -LiteralPath $path -Value ($Receipt | ConvertTo-Json -Depth 12) -Encoding UTF8
  $sha = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
  Set-Content -LiteralPath ($path + '.sha256') -Value ("{0}  {1}" -f $sha, (Split-Path -Leaf $path)) -Encoding ASCII

  return [pscustomobject]@{ receiptPath = $path; receiptSha256 = $sha }
}

# ── Main entry point ───────────────────────────────────────────────────────────

function Invoke-DivisionWithReceipt {
  [CmdletBinding()]
  param(
    [Parameter(Mandatory)] [string]$DivisionName,
    [switch]$RunBaseline,
    [string[]]$Args = @()
  )

  $root    = Get-SquadBatRoot
  $headSha = Get-SquadBatHeadSha -Root $root

  # ── 1. Founding law verification — fail closed ─────────────────────────────
  try {
    $lawHash = Assert-FoundingLaw -Root $root
  } catch {
    Write-Host "DIVISION_BLOCKED: $_"
    return [pscustomobject]@{ exitCode = 10; receiptPath = ''; root = $root; blockedBy = 'founding_law' }
  }

  # ── 2. Resolve Division entry ──────────────────────────────────────────────
  $cfg      = Resolve-DivisionConfig -Root $root -DivisionName $DivisionName
  $entryRaw = $cfg.entry

  if ([string]::IsNullOrWhiteSpace($entryRaw)) {
    $envName = ('SQUAD_BAT_DIVISION_ENTRY_{0}' -f $DivisionName.ToUpperInvariant() -replace '-','_')
    $envVal  = [Environment]::GetEnvironmentVariable($envName)
    if (-not [string]::IsNullOrWhiteSpace($envVal)) { $entryRaw = $envVal }
  }

  if ([string]::IsNullOrWhiteSpace($entryRaw)) {
    Write-Host ("{0}: not configured (divisions.json entry empty and no SQUAD_BAT_DIVISION_ENTRY_* override)" -f $DivisionName)
    return [pscustomobject]@{ exitCode = 2; receiptPath = ''; root = $root }
  }

  $entryPath = Resolve-DivisionEntry -Entry $entryRaw
  if ([string]::IsNullOrWhiteSpace($entryPath) -or (-not (Test-Path -LiteralPath $entryPath))) {
    Write-Host ("{0}: configured entry not found: {1}" -f $DivisionName, $entryRaw)
    return [pscustomobject]@{ exitCode = 3; receiptPath = ''; root = $root }
  }

  $entrySha     = Get-EntrySha256 -EntryPath $entryPath
  $baselineLabel = ("squad-bat_{0}_{1}" -f $DivisionName, (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ'))
  $ts            = Get-IsoTimestampUtc

  # ── 3. Baseline PRE ────────────────────────────────────────────────────────
  $pre = $null
  if ($RunBaseline) {
    $pre = Invoke-BaselinePhase -Mode 'pre' -Root $root -Label $baselineLabel
  }

  # ── 4. Invoke Division ─────────────────────────────────────────────────────
  $exec = Invoke-ExternalDivision -EntryPath $entryPath -Type $cfg.type -EntryArgs $Args

  # ── 5. Baseline POST ───────────────────────────────────────────────────────
  $post = $null
  if ($RunBaseline) {
    $post = Invoke-BaselinePhase -Mode 'post' -Root $root -Label $baselineLabel
  }

  # ── 6. Ygg ledger receipt — outcome only, zero PII ────────────────────────
  $ygg = Invoke-YggReceipt -Root $root -DivisionName $DivisionName -ExitCode $exec.exitCode -Timestamp $ts

  # ── 7. JSON receipt file ───────────────────────────────────────────────────
  $receipt = [ordered]@{
    schema             = 'squad-bat.division-receipt.v1'
    timestamp          = $ts
    founding_law_sha256 = $lawHash
    squad_bat = [ordered]@{
      root    = $root
      headSha = $headSha
    }
    division = [ordered]@{
      name        = $DivisionName
      entryPath   = $entryPath
      entrySha256 = $entrySha
      type        = $cfg.type
    }
    execution = [ordered]@{
      kind     = $exec.kind
      workDir  = $exec.workDir
      exitCode = $exec.exitCode
      stdout   = $exec.stdout
      stderr   = $exec.stderr
    }
    baseline = [ordered]@{
      enabled = $RunBaseline.IsPresent
      label   = $baselineLabel
      pre     = if ($pre)  { $pre  } else { [pscustomobject]@{ enabled = $false } }
      post    = if ($post) { $post } else { [pscustomobject]@{ enabled = $false } }
    }
    ygg = [ordered]@{
      enabled = $ygg.enabled
      reason  = $ygg.reason
    }
  }

  $written = Write-DivisionReceipt -Root $root -DivisionName $DivisionName -Receipt $receipt

  return [pscustomobject]@{
    exitCode      = $exec.exitCode
    receiptPath   = $written.receiptPath
    receiptSha256 = $written.receiptSha256
    root          = $root
  }
}
