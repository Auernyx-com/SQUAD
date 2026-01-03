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

# Repo-local shim to keep launchers stable.
# Delegates to the authoritative baseline tool installed at C:\baseline-algorithms-and-programs.

if (-not $ProjectRoot -or -not $ProjectRoot.Trim()) {
  $ProjectRoot = (Get-Location).Path
}

$projectFull = [System.IO.Path]::GetFullPath($ProjectRoot)
Write-Output ("BASELINE_CONTEXT: Mode={0} Label={1} ProjectRoot={2}" -f $Mode, $Label, $projectFull)

$porcelainIsEmpty = $null

try {
  $gitTopLines = & git -C $projectFull rev-parse --show-toplevel 2>$null
  $gitExit = $LASTEXITCODE
  $gitTop = $null
  if ($gitTopLines) {
    $gitTop = [string]($gitTopLines | Select-Object -First 1)
  }

  if ($gitExit -eq 0 -and $gitTop -and $gitTop.Trim()) {
    $gitTopFull = [System.IO.Path]::GetFullPath($gitTop.Trim())
    Write-Output ("BASELINE_GIT: toplevel={0}" -f $gitTopFull)

    if (-not $gitTopFull.Equals($projectFull, [System.StringComparison]::OrdinalIgnoreCase)) {
      Write-Output ("BASELINE_GIT_WARN: ProjectRoot differs from git toplevel (ProjectRoot={0} toplevel={1})" -f $projectFull, $gitTopFull)
    }

    Write-Output "BASELINE_GIT_PORCELAIN_BEGIN"
    $porcelain = (& git -C $gitTopFull status --porcelain)
    $porcelainIsEmpty = -not ($porcelain -and $porcelain.Count -gt 0)
    if ($porcelain -and $porcelain.Count -gt 0) {
      foreach ($line in $porcelain) { Write-Output ([string]$line) }
    } else {
      Write-Output "(empty)"
    }
    Write-Output "BASELINE_GIT_PORCELAIN_END"
  } else {
    Write-Output "BASELINE_GIT_WARN: ProjectRoot is not a git repo (or git not available)."
  }
} catch {
  Write-Output ("BASELINE_GIT_WARN: Failed to probe git context: {0}" -f $_.Exception.Message)
}

$External = "C:\baseline-algorithms-and-programs\baseline.ps1"
if (-not (Test-Path -LiteralPath $External)) {
  throw "Missing external baseline tool: $External"
}

# Forward all supported args explicitly (keeps parameter binding predictable).
$baselineOutput = & powershell -NoProfile -ExecutionPolicy Bypass -File $External `
  $Mode `
  -Label $Label `
  $(if ($Commit) { "-Commit" } else { $null }) `
  $(if ($VerifyHashes) { "-VerifyHashes" } else { $null }) `
  -ProjectRoot $ProjectRoot `
  -LedgerRoot $LedgerRoot 2>&1

$exitCode = $LASTEXITCODE

$reportedCleanMismatchFlagged = $false

foreach ($line in $baselineOutput) {
  $text = [string]$line

  if (-not $reportedCleanMismatchFlagged -and $porcelainIsEmpty -eq $false -and ($text -match 'working tree clean')) {
    Write-Output 'BASELINE_GIT_MISMATCH: External baseline output claims clean, but shim porcelain above is non-empty. Treat external claim as non-authoritative.'
    $reportedCleanMismatchFlagged = $true
  }

  # Suppress noisy/commonly-stale git remote status hints emitted by the external tool.
  if ($text -match "^Your branch is behind 'origin/main' by\\s+\\d+\\s+commits" ) { continue }
  if ($text -match '^\s*\(use "git pull" to update your local branch\)\s*$') { continue }

  Write-Output $line
}

exit $exitCode
