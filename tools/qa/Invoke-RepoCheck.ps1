<#!
.SYNOPSIS
  Repo-wide sanity checks (PowerShell parse, JSON parse, Python compile).

.DESCRIPTION
  Runs a minimal, repeatable repo check without writing to OUTPUTS/.
  Designed for PS 5.1 compatibility.

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\qa\Invoke-RepoCheck.ps1

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\qa\Invoke-RepoCheck.ps1 -IncludeOutputs
#>

[CmdletBinding()]
param(
  [switch]$IncludeOutputs,
  [int]$MaxFailures = 50
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-RepoRoot {
  $here = Resolve-Path -LiteralPath $PSScriptRoot
  return (Resolve-Path -LiteralPath (Join-Path $here '..\..')).Path
}

function Get-PythonPath([string]$Root) {
  $py = Join-Path $Root '.venv\Scripts\python.exe'
  if (Test-Path -LiteralPath $py) { return $py }

  throw "Python venv not found at: $py"
}

function Run-Step([string]$Label, [scriptblock]$Action) {
  Write-Host ("[RUN] {0}" -f $Label)
  & $Action
  Write-Host ("[OK ] {0}" -f $Label)
}

$root = Get-RepoRoot
$py = Get-PythonPath -Root $root

$jsonSweep = Join-Path $root 'tools\qa\json_sweep.py'
$pyCompile = Join-Path $root 'tools\qa\python_compile_sweep.py'
$moduleRegistryCheck = Join-Path $root 'tools\qa\validate_module_registries.py'
$repoIdentityCheck = Join-Path $root 'tools\qa\verify_squad_repo.py'
$changeClassifier = Join-Path $root 'tools\qa\classify_changes.py'

if (-not (Test-Path -LiteralPath $jsonSweep)) { throw "Missing: $jsonSweep" }
if (-not (Test-Path -LiteralPath $pyCompile)) { throw "Missing: $pyCompile" }
if (-not (Test-Path -LiteralPath $moduleRegistryCheck)) { throw "Missing: $moduleRegistryCheck" }
if (-not (Test-Path -LiteralPath $repoIdentityCheck)) { throw "Missing: $repoIdentityCheck" }
if (-not (Test-Path -LiteralPath $changeClassifier)) { throw "Missing: $changeClassifier" }

$skipOutputs = -not $IncludeOutputs

$failures = New-Object System.Collections.Generic.List[object]

# 0) Repo identity / context check (Phase 1: Repo Awareness)
Run-Step 'Repo identity (SQUAD)' {
  & $py $repoIdentityCheck
  if ($LASTEXITCODE -ne 0) {
    $failures.Add([pscustomobject]@{ Type = 'repo-identity'; Path = $root; Detail = 'Repo is not recognized as SQUAD (see JSON output above).' })
  }
}

# 0.5) Phase 2: Artifact classification + boundary crossing warnings
Run-Step 'Artifact classification (working tree)' {
  & $py $changeClassifier
  if ($LASTEXITCODE -ne 0) {
    $failures.Add([pscustomobject]@{ Type = 'artifact-classification'; Path = $root; Detail = 'Artifact classification reported errors/warnings (see JSON output above).' })
  }
}

# 1) PowerShell parse check
Run-Step 'PowerShell parse (.ps1)' {
  $ps1Files = Get-ChildItem -LiteralPath $root -Recurse -Filter *.ps1 -File |
    Where-Object {
      $_.FullName -notmatch '\\\.venv\\' -and
      $_.FullName -notmatch '\\\.git\\' -and
      $_.FullName -notmatch '\\node_modules\\' -and
      (-not $skipOutputs -or $_.FullName -notmatch '\\OUTPUTS\\')
    }

  foreach ($f in $ps1Files) {
    $tokens = $null
    $parseErrors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile($f.FullName, [ref]$tokens, [ref]$parseErrors)
    if ($parseErrors -and $parseErrors.Count -gt 0) {
      foreach ($e in $parseErrors) {
        $failures.Add([pscustomobject]@{
          Type = 'ps-parse'
          Path = $f.FullName
          Detail = $e.Message
        })
      }
    }
  }
}

# 2) JSON parse sweep (Python)
Run-Step 'JSON parse (.json)' {
  $args = @(
    $jsonSweep,
    '--root', $root,
    '--max-failures', [string]$MaxFailures
  )
  if ($IncludeOutputs) {
    $args += '--include-outputs'
  }

  & $py @args
  if ($LASTEXITCODE -ne 0) {
    $failures.Add([pscustomobject]@{ Type = 'json-parse'; Path = $root; Detail = 'One or more JSON files failed to parse (see output above).' })
  }
}

# 3) Python compile sweep
Run-Step 'Python compile (.py)' {
  & $py $pyCompile --root $root
  if ($LASTEXITCODE -ne 0) {
    $failures.Add([pscustomobject]@{ Type = 'py-compile'; Path = $root; Detail = 'One or more Python files failed to compile.' })
  }
}

# 4) Module registry entrypoint validation
Run-Step 'Module registry entrypoints' {
  & $py $moduleRegistryCheck
  if ($LASTEXITCODE -ne 0) {
    $failures.Add([pscustomobject]@{ Type = 'module-registry'; Path = $root; Detail = 'One or more module registry entrypoints are invalid/missing (see output above).' })
  }
}

Write-Host ''
Write-Host '=== SUMMARY ==='
Write-Host ("Root: {0}" -f $root)
Write-Host ("Failures: {0}" -f $failures.Count)

if ($failures.Count -gt 0) {
  Write-Host ''
  Write-Host '=== FAILURES (first 50) ==='
  $failures | Select-Object -First 50 | ForEach-Object {
    Write-Host ("{0} :: {1} :: {2}" -f $_.Type, $_.Path, $_.Detail)
  }
  exit 1
}

exit 0
