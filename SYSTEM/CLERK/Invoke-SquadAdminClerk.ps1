<#
.SYNOPSIS
  Delegate wrapper for the authoritative SQUAD Admin Clerk.

.DESCRIPTION
  The ONLY authoritative Clerk entrypoint is the repo-root script:
    Invoke-SquadAdminClerk.ps1

  This file must not diverge in behavior. It exists only as a convenience shim
  for callers that expect a SYSTEM\CLERK path.
#>

[CmdletBinding()]
param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$PassThruArgs
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\.."))
$authoritative = Join-Path $repoRoot "Invoke-SquadAdminClerk.ps1"

if (-not (Test-Path -LiteralPath $authoritative)) {
  throw "Missing authoritative Clerk entrypoint: $authoritative"
}

try {
  & $authoritative @PassThruArgs
  exit 0
} catch {
  Write-Error $_
  exit 1
}
