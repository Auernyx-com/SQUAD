[CmdletBinding()]
param(
  [Parameter(Mandatory=$true, Position=0)]
  [ValidateSet("pre","post","verify")]
  [string]$Mode,

  [string]$Label = "",

  [switch]$Commit,

  [switch]$VerifyHashes,

  [string]$ProjectRoot,

  [string]$LedgerRoot
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$Marker = Join-Path $RepoRoot ".baseline-repo.marker"
if (-not (Test-Path $Marker)) { throw "Not a baseline repo root (missing .baseline-repo.marker): $RepoRoot" }

$CaptureScript = Join-Path $RepoRoot "scripts\modules\Invoke-BaselineStateCapture.ps1"
if (-not (Test-Path $CaptureScript)) { throw "Missing module: $CaptureScript" }

# Determine ledger location (where authoritative artifacts are stored)
if ([string]::IsNullOrWhiteSpace($LedgerRoot)) {
  $LedgerRoot = $env:BASELINE_LEDGER_ROOT
}
if ([string]::IsNullOrWhiteSpace($LedgerRoot)) {
  $LedgerRoot = $RepoRoot
}
$LedgerRoot = (Resolve-Path -LiteralPath $LedgerRoot).Path

$ArtifactsRoot = Join-Path $LedgerRoot "artifacts\statecapture"
$ReportsRoot   = Join-Path $LedgerRoot "artifacts\reports"
New-Item -ItemType Directory -Path $ReportsRoot -Force | Out-Null

function Write-BaselineReceipt {
  param(
    [Parameter(Mandatory)] [string] $ProjectRoot,
    [Parameter(Mandatory)] [ValidateSet("pre","post")] [string] $Mode,
    [Parameter(Mandatory)] [string] $RepoRoot,
    [Parameter(Mandatory)] [string] $Label,
    [Parameter(Mandatory)] [hashtable] $Data
  )

  if ([string]::IsNullOrWhiteSpace($ProjectRoot)) { return }

  $Proj = (Resolve-Path -LiteralPath $ProjectRoot).Path
  $OutDir = Join-Path $Proj ".baseline"
  New-Item -ItemType Directory -Path $OutDir -Force | Out-Null

  $okName = "last-$Mode.ok.json"
  $jsonPath = Join-Path $OutDir $okName

  $payload = [ordered]@{
    schema        = "baseline-receipt.v1"
    mode          = $Mode
    label         = $Label
    projectRoot   = $Proj
    baselineRoot  = $RepoRoot
    timestampUtc  = (Get-Date).ToUniversalTime().ToString("o")
    data          = $Data
  }

  $json = ($payload | ConvertTo-Json -Depth 10)
  Set-Content -LiteralPath $jsonPath -Value $json -Encoding UTF8

  $hash = (Get-FileHash -LiteralPath $jsonPath -Algorithm SHA256).Hash.ToLowerInvariant()
  $shaPath = Join-Path $OutDir "$okName.sha256"
  Set-Content -LiteralPath $shaPath -Value "$hash  $okName" -Encoding ASCII
}

function Get-LatestBundle([string]$phase) {
  if (-not (Test-Path $ArtifactsRoot)) { return $null }
  $dirs = Get-ChildItem -Path $ArtifactsRoot -Directory |
    Where-Object { $_.Name -match ("-{0}-" -f $phase) } |
    Sort-Object Name
  if ($dirs.Count -eq 0) { return $null }
  return $dirs[-1].FullName
}

function Read-CsvSafe([string]$path) {
  if (Test-Path $path) { return Import-Csv $path } else { return @() }
}

function Write-ReportMd([string]$preDir, [string]$postDir, [string]$outPath) {
  $preManifest  = Join-Path $preDir  "manifest.json"
  $postManifest = Join-Path $postDir "manifest.json"

  $preM  = if (Test-Path $preManifest)  { Get-Content $preManifest  -Raw | ConvertFrom-Json } else { $null }
  $postM = if (Test-Path $postManifest) { Get-Content $postManifest -Raw | ConvertFrom-Json } else { $null }

  $lines = New-Object System.Collections.Generic.List[string]
  $lines.Add("# Baseline Drift Report")
  $lines.Add("")
   $lines.Add(('Generated (local): {0}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')))

  if ($preM -and $postM) {
    $lines.Add(('PRE: {0} | POST: {1}' -f $preM.timestamp_local, $postM.timestamp_local))
    $lines.Add(('PRE Dir: {0}' -f ($preDir.Substring($RepoRoot.Length + 1))))
    $lines.Add(('POST Dir: {0}' -f ($postDir.Substring($RepoRoot.Length + 1))))
  }
  $lines.Add("")


  # --- Services diff ---
  $preServices  = Read-CsvSafe (Join-Path $preDir  "services.csv")
  $postServices = Read-CsvSafe (Join-Path $postDir "services.csv")

  $preSvcMap  = @{}; foreach ($s in $preServices)  { $preSvcMap[$s.Name]  = $s }
  $postSvcMap = @{}; foreach ($s in $postServices) { $postSvcMap[$s.Name] = $s }

  $addedSvcs   = $postSvcMap.Keys | Where-Object { -not $preSvcMap.ContainsKey($_) } | Sort-Object
  $removedSvcs = $preSvcMap.Keys  | Where-Object { -not $postSvcMap.ContainsKey($_) } | Sort-Object
  $changedSvcs = $postSvcMap.Keys | Where-Object {
    $preSvcMap.ContainsKey($_) -and (
      $preSvcMap[$_].Status    -ne $postSvcMap[$_].Status -or
      $preSvcMap[$_].StartType -ne $postSvcMap[$_].StartType
    )
  } | Sort-Object

  $lines.Add("## Services")
  $lines.Add("")
  $lines.Add(("- Added: **{0}**  | Removed: **{1}**  | Changed: **{2}**" -f $addedSvcs.Count, $removedSvcs.Count, $changedSvcs.Count))
  $lines.Add("")

  if ($addedSvcs.Count -gt 0) {
    $lines.Add("### Added services")
    foreach ($name in $addedSvcs) { $lines.Add(("- {0}" -f $name)) }
    $lines.Add("")
  }
  if ($removedSvcs.Count -gt 0) {
    $lines.Add("### Removed services")
    foreach ($name in $removedSvcs) { $lines.Add(("- {0}" -f $name)) }
    $lines.Add("")
  }
  if ($changedSvcs.Count -gt 0) {
    $lines.Add("### Changed services")
    foreach ($name in $changedSvcs) {
      $a = $preSvcMap[$name]; $b = $postSvcMap[$name]
      $lines.Add(("- {0}: Status {1} -> {2}, StartType {3} -> {4}" -f $name, $a.Status, $b.Status, $a.StartType, $b.StartType))
    }
    $lines.Add("")
  }

  # --- Scheduled tasks diff (keys only) ---
  $preTasks  = Read-CsvSafe (Join-Path $preDir  "scheduledtasks.csv")
  $postTasks = Read-CsvSafe (Join-Path $postDir "scheduledtasks.csv")

  $preTaskKey  = $preTasks  | ForEach-Object { "{0}{1}" -f $_.TaskPath, $_.TaskName } | Sort-Object -Unique
  $postTaskKey = $postTasks | ForEach-Object { "{0}{1}" -f $_.TaskPath, $_.TaskName } | Sort-Object -Unique

  $addedTasks   = Compare-Object $preTaskKey $postTaskKey -PassThru | Where-Object { $_ -in $postTaskKey }
  $removedTasks = Compare-Object $preTaskKey $postTaskKey -PassThru | Where-Object { $_ -in $preTaskKey }

  $lines.Add("## Scheduled Tasks")
  $lines.Add("")
  $lines.Add(("- Added: **{0}**  | Removed: **{1}**" -f $addedTasks.Count, $removedTasks.Count))
  $lines.Add("")

  if ($addedTasks.Count -gt 0) {
    $lines.Add("### Added tasks (keys)")
    foreach ($t in $addedTasks) { $lines.Add(("- {0}" -f $t)) }
    $lines.Add("")
  }
  if ($removedTasks.Count -gt 0) {
    $lines.Add("### Removed tasks (keys)")
    foreach ($t in $removedTasks) { $lines.Add(("- {0}" -f $t)) }
    $lines.Add("")
  }

  # --- Firewall profile diff (simple line diff) ---
  $preFw  = Join-Path $preDir  "firewall_profiles.txt"
  $postFw = Join-Path $postDir "firewall_profiles.txt"

  $lines.Add("## Firewall Profiles")
  $lines.Add("")
  if ((Test-Path $preFw) -and (Test-Path $postFw)) {
    $a = Get-Content $preFw
    $b = Get-Content $postFw
    $diff = Compare-Object $a $b -PassThru
    if ($diff.Count -eq 0) {
      $lines.Add("- No changes detected.")
    } else {
      $lines.Add("- Differences detected (raw line diff):")
      $lines.Add("")
           $lines.Add("---- Firewall line diff ----")
      foreach ($d in $diff) { $lines.Add($d) }
      $lines.Add("---- end diff ----")

    }
  } else {
    $lines.Add("- Missing firewall_profiles.txt in one or both bundles.")
  }
  $lines.Add("")

  $lines | Out-File -FilePath $outPath -Encoding utf8
}

function Verify-BundleHashes([string]$bundleDir) {
  $hashFile = Join-Path $bundleDir "hashes.sha256"
  if (-not (Test-Path $hashFile)) { throw "Missing hashes.sha256 in $bundleDir" }

  $lines = Get-Content $hashFile | Where-Object { $_.Trim() -ne "" }
  $bad = 0
  foreach ($line in $lines) {
    $parts = $line -split "\s\s+", 2
    if ($parts.Count -ne 2) { continue }
    $expected = $parts[0].Trim()
    $path = $parts[1].Trim()
    # Hash file contains absolute paths
    if (-not (Test-Path $path)) { $bad++; continue }
    $actual = (Get-FileHash -Algorithm SHA256 -Path $path).Hash
    if ($actual -ne $expected) { $bad++ }
  }
  return $bad
}

if ($Mode -eq "verify") {
  $latestPost = Get-LatestBundle "POST"
  if (-not $latestPost) { throw "No POST bundles found to verify." }
  $bad = Verify-BundleHashes $latestPost
  if ($bad -eq 0) { Write-Host ("OK: hashes verified for {0}" -f $latestPost) }
  else { throw ("Hash verification failed: {0} mismatches" -f $bad) }
  exit 0
}

if ($Mode -eq "pre") {
  Push-Location $RepoRoot
  try {
    $env:BASELINE_ARTIFACTS_ROOT = $ArtifactsRoot
    & $CaptureScript -Phase PRE -Label $Label
    Write-Host "PRE capture complete."
    if ($ProjectRoot) {
      Write-BaselineReceipt -ProjectRoot $ProjectRoot -Mode "pre" -RepoRoot $RepoRoot -Label $Label -Data @{
        baselineCommit = (git -C $RepoRoot rev-parse HEAD 2>$null)
        ledgerRoot     = $LedgerRoot
      }
    }
    if ($Commit) {
      git add .
      git commit -m ("chore: baseline PRE capture {0}" -f $Label)
    }
  } finally {
    Remove-Item env:BASELINE_ARTIFACTS_ROOT -ErrorAction SilentlyContinue
    Pop-Location
  }
  exit 0
}

if ($Mode -eq "post") {
  $latestPre = Get-LatestBundle "PRE"
  if (-not $latestPre) { throw "No PRE bundle found. Run: .\baseline.ps1 pre" }

  Push-Location $RepoRoot
  try {
    $env:BASELINE_ARTIFACTS_ROOT = $ArtifactsRoot
    & $CaptureScript -Phase POST -Label $Label

    $latestPost = Get-LatestBundle "POST"
    if (-not $latestPost) { throw "POST bundle not found after capture." }

    if ($VerifyHashes) {
      $badPre  = Verify-BundleHashes $latestPre
      $badPost = Verify-BundleHashes $latestPost
      if ($badPre -ne 0 -or $badPost -ne 0) {
        throw ("Hash verify failed. PRE bad={0} POST bad={1}" -f $badPre, $badPost)
      }
    }

    $reportName = "drift-{0}_TO_{1}.md" -f (Split-Path $latestPre -Leaf), (Split-Path $latestPost -Leaf)
    $reportPath = Join-Path $ReportsRoot $reportName
    Write-ReportMd -preDir $latestPre -postDir $latestPost -outPath $reportPath

    Write-Host "POST capture complete."
    Write-Host ("Drift report: {0}" -f $reportPath)

    if ($ProjectRoot) {
      Write-BaselineReceipt -ProjectRoot $ProjectRoot -Mode "post" -RepoRoot $RepoRoot -Label $Label -Data @{
        baselineCommit = (git -C $RepoRoot rev-parse HEAD 2>$null)
        verifyHashes   = [bool]$VerifyHashes
        ledgerRoot     = $LedgerRoot
      }
    }

    if ($Commit) {
      git add .
      git commit -m ("feat: baseline POST capture + drift report {0}" -f $Label)
    }
  } finally {
    Remove-Item env:BASELINE_ARTIFACTS_ROOT -ErrorAction SilentlyContinue
    Pop-Location
  }
  exit 0
}
