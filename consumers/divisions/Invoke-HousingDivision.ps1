[CmdletBinding()]
param(
  [string[]] $Args = @()
)

$ErrorActionPreference = 'Stop'

$lib = Join-Path $PSScriptRoot 'lib\DivisionInvoke.ps1'
. $lib

$result = Invoke-DivisionWithReceipt -DivisionName 'housing-division' -Args $Args
exit $result.exitCode
