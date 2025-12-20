@'
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true, Position=0)]
  [ValidateSet("pre","post","verify")]
  [string]$Mode,

  [string]$Label = "",

  [switch]$Commit,

  [switch]$VerifyHashes
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Get-Location).Path
$Marker = Join-Path $RepoRoot ".baseline-repo.marker"
if (-not (Test-Path $Marker)) { throw "Not a baseline repo root (missing .baseline-repo.marker)." }

$CaptureScript = Join-Path $RepoRoot "scripts\modules\Invoke-BaselineStateCapture.ps1"
if (-not (Test-Path $CaptureScript)) { throw "Missing module: $CaptureScript" }

$ArtifactsRoot = Join-Path $RepoRoot "artifacts\statecapture"
$ReportsRoot   = Join-Path $RepoRoot "artifacts\reports"
New-Item -ItemType Directory -Path $ReportsRoot -Force | Out-Null

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
  $lines.Add(("**Generated (local):** {0}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss")))

  if ($preM -and $postM) {
    $lines.Add(("**PRE:** {0}  | **POST:** {1}" -f $preM.timestamp_local, $postM.timestamp_local))
    $lines.Add(("**PRE Dir:** `{0}`" -f ($preDir.Substring($RepoRoot.Length + 1))))
    $lines.Add(("**POST Dir:** `{0}`" -f ($postDir.Substring($RepoRoot.Length + 1))))
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
      $lines.Add("```")
      foreach ($d in $diff) { $lines.Add($d) }
      $lines.Add("```")
    }
  } else {
    $lines.Add("- Missing firewall_profiles.txt in one or both bundles.")
  }
  $lines.Add("")

  $lines | Out-File -Path $outPath -Encoding utf8
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
    $rel = $parts[1].Trim()
    $abs = Join-Path $RepoRoot $rel
    if (-not (Test-Path $abs)) { $bad++; continue }
    $actual = (Get-FileHash -Algorithm SHA256 -Path $abs).Hash
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
  & $CaptureScript -Phase PRE -Label $Label
  Write-Host "PRE capture complete."
  if ($Commit) {
    git add .
    git commit -m ("chore: baseline PRE capture {0}" -f $Label)
  }
  exit 0
}

if ($Mode -eq "post") {
  $latestPre = Get-LatestBundle "PRE"
  if (-not $latestPre) { throw "No PRE bundle found. Run: .\baseline.ps1 pre" }

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

  if ($Commit) {
    git add .
    git commit -m ("feat: baseline POST capture + drift report {0}" -f $Label)
  }
  exit 0
}
'@ | Set-Content -Path .\baseline.ps1 -Encoding utf8
