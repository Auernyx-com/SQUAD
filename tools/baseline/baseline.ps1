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

foreach ($line in $baselineOutput) {
  $text = [string]$line

  # Suppress noisy/commonly-stale git remote status hints emitted by the external tool.
  if ($text -match "^Your branch is behind 'origin/main' by\\s+\\d+\\s+commits" ) { continue }
  if ($text -match '^\s*\(use "git pull" to update your local branch\)\s*$') { continue }

  Write-Output $line
}

exit $exitCode
