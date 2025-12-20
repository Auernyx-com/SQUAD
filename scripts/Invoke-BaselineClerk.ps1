[CmdletBinding(SupportsShouldProcess)]
param(
    [switch]$Init,
    [switch]$VerifyOnly,
    [switch]$EmitHashes
)

# -------------------------------
# Constants (hard guardrails)
# -------------------------------
$RepoMarker = ".baseline-repo.marker"
$AllowedDirs = @("docs", "artifacts", "scripts", "logs")
$ScriptVersion = "1.0.0"

$RepoRoot = (Get-Location).Path
$LogDir = Join-Path $RepoRoot "logs"
$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$LogFile = Join-Path $LogDir "baseline-clerk-$Timestamp.log"

# -------------------------------
# Safety checks
# -------------------------------
function Throw-Fatal($msg) {
    Write-Error $msg
    exit 1
}

function Assert-InRepoRoot {
    if (-not (Test-Path $RepoRoot)) {
        Throw-Fatal "Repo root does not exist."
    }
}

function Assert-MarkerExists {
    if (-not (Test-Path (Join-Path $RepoRoot $RepoMarker))) {
        Throw-Fatal "Baseline marker missing. Refusing to run without -Init."
    }
}

function Assert-SafePath($path) {
    $full = [System.IO.Path]::GetFullPath($path)
    if (-not $full.StartsWith($RepoRoot)) {
        Throw-Fatal "Path escape detected: $path"
    }
}

# -------------------------------
# Logging
# -------------------------------
function Write-Log($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format "u"), $msg
    Add-Content -Path $LogFile -Value $line
}

# -------------------------------
# Hash helper
# -------------------------------
function Write-Hash($target) {
    $hash = Get-FileHash -Algorithm SHA256 -Path $target
    $hash.Path | Out-File "$($target).sha256"
    $hash.Hash | Add-Content "$($target).sha256"
}

# -------------------------------
# Execution
# -------------------------------
Assert-InRepoRoot

if (-not $Init) {
    Assert-MarkerExists
}

# Ensure log dir exists
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

Write-Log "Invoke-BaselineClerk v$ScriptVersion"
Write-Log "RepoRoot: $RepoRoot"
Write-Log "Init=$Init VerifyOnly=$VerifyOnly EmitHashes=$EmitHashes"

if ($Init) {
    if (-not (Test-Path (Join-Path $RepoRoot $RepoMarker))) {
        Write-Log "Creating baseline marker"
        New-Item -ItemType File -Path (Join-Path $RepoRoot $RepoMarker) | Out-Null
    }

    foreach ($dir in $AllowedDirs) {
        $target = Join-Path $RepoRoot $dir
        Assert-SafePath $target

        if (-not (Test-Path $target)) {
            Write-Log "Creating directory: $dir"
            New-Item -ItemType Directory -Path $target | Out-Null
            New-Item -ItemType File -Path (Join-Path $target ".gitkeep") | Out-Null
        } else {
            Write-Log "Directory exists: $dir"
        }
    }
}

if ($VerifyOnly) {
    foreach ($dir in $AllowedDirs) {
        $target = Join-Path $RepoRoot $dir
        if (-not (Test-Path $target)) {
            Throw-Fatal "Missing required directory: $dir"
        }
    }
    Write-Log "Verification passed"
}

if ($EmitHashes) {
    Write-Log "Emitting hashes"
    Write-Hash $LogFile
    if (Test-Path (Join-Path $RepoRoot $RepoMarker)) {
        Write-Hash (Join-Path $RepoRoot $RepoMarker)
    }
}

Write-Log "Baseline clerk completed successfully"
