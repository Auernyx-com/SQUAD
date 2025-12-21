[CmdletBinding(SupportsShouldProcess=$true)]
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
function Write-BaselineError {
    [CmdletBinding()]
    param(
        [string]$Message
    )
    Write-Error $Message
    exit 1
}

function Assert-InRepoRoot {
    if (-not (Test-Path $RepoRoot)) {
        Stop-Baseline "Repo root does not exist."
    }
}

function Assert-BaselineMarker {
    if (-not (Test-Path (Join-Path $RepoRoot $RepoMarker))) {
        Stop-Baseline "Baseline marker missing. Refusing to run without -Init."
    }
}

function Assert-SafePath($path) {
    $full = [System.IO.Path]::GetFullPath($path)
    if (-not $full.StartsWith($RepoRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        Stop-Baseline "Path escape detected: $path"
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
function Write-Hash {
    [CmdletBinding(SupportsShouldProcess=$true)]
    param(
        [string]$target
    )
    $hash = Get-FileHash -Algorithm SHA256 -Path $target
    $rel = $hash.Path
    if ([System.IO.Path].GetMethod("GetRelativePath")) {
        try {
            $rel = [System.IO.Path]::GetRelativePath($RepoRoot, $rel)
        } catch {
                if ($rel.StartsWith($RepoRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
                $rel = $rel.Substring($RepoRoot.Length).TrimStart([char]92,[char]47)
            }
        }
    } else {
        if ($rel.StartsWith($RepoRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            $rel = $rel.Substring($RepoRoot.Length).TrimStart([char]92,[char]47)
        }
    }
    $outPath = "$($target).sha256"
    if ($PSCmdlet.ShouldProcess($outPath, 'Write hash file')) {
        "{0}  {1}" -f $hash.Hash, $rel | Out-File $outPath -Encoding utf8
        Write-Verbose "Wrote hash file: $outPath"
    }
}

# -------------------------------
# Execution
# -------------------------------
Assert-InRepoRoot

    if (-not $Init) {
    Assert-BaselineMarker
}

# Ensure log dir exists
if (-not (Test-Path $LogDir)) {
    if ($PSCmdlet.ShouldProcess($LogDir, 'Create log directory')) {
        New-Item -ItemType Directory -Path $LogDir | Out-Null
        Write-Verbose "Created log directory: $LogDir"
    }
}

Write-Log "Invoke-BaselineClerk v$ScriptVersion"
Write-Log "RepoRoot: $RepoRoot"
Write-Log "Init=$Init VerifyOnly=$VerifyOnly EmitHashes=$EmitHashes"

if ($Init) {
    if (-not (Test-Path (Join-Path $RepoRoot $RepoMarker))) {
        $markerPath = (Join-Path $RepoRoot $RepoMarker)
        if ($PSCmdlet.ShouldProcess($markerPath, 'Create baseline marker')) {
            Write-Log "Creating baseline marker"
            New-Item -ItemType File -Path $markerPath | Out-Null
            Write-Verbose "Created baseline marker: $markerPath"
        }
    }

    foreach ($dir in $AllowedDirs) {
        $target = Join-Path $RepoRoot $dir
        Assert-SafePath $target

        if (-not (Test-Path $target)) {
            if ($PSCmdlet.ShouldProcess($target, "Create directory $dir")) {
                Write-Log "Creating directory: $dir"
                New-Item -ItemType Directory -Path $target | Out-Null
                New-Item -ItemType File -Path (Join-Path $target ".gitkeep") | Out-Null
                Write-Verbose "Created directory and .gitkeep: $target"
            }
        } else {
            Write-Log "Directory exists: $dir"
        }
    }
}

if ($VerifyOnly) {
    foreach ($dir in $AllowedDirs) {
        $target = Join-Path $RepoRoot $dir
        if (-not (Test-Path $target)) {
            Stop-Baseline "Missing required directory: $dir"
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
