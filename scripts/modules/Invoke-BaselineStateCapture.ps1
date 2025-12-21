[CmdletBinding(SupportsShouldProcess=$true)]
param(
    [ValidateSet("PRE","POST")]
    [string]$Phase = "PRE",

    [string]$Label = ""
)

$RepoMarker = ".baseline-repo.marker"
$RepoRoot = (Get-Location).Path
$MarkerPath = Join-Path $RepoRoot $RepoMarker

function Write-BaselineError {
    [CmdletBinding()]
    param(
        [string]$Message
    )
    Write-Error $Message
    exit 1
}

function Assert-RepoRoot {
    if (-not (Test-Path $MarkerPath)) {
        Write-BaselineError -Message "Baseline marker missing. Refusing to run outside a baseline repo root."
    }
}

function Assert-SafePath($path) {
    $full = [System.IO.Path]::GetFullPath($path)
    if (-not $full.StartsWith($RepoRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        Write-BaselineError -Message "Path escape detected: $path"
    }
}

function Write-FileHashList($targetDir, $outFile) {
  $items = Get-ChildItem -Path $targetDir -File -Recurse |
    Where-Object { $_.Name -notin @("run.log", "hashes.sha256") } |
    Sort-Object FullName


    $lines = foreach ($f in $items) {
        $h = Get-FileHash -Algorithm SHA256 -Path $f.FullName
                $rel = $h.Path
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
                $entry = "{0}  {1}" -f $h.Hash, $rel
                $entry
    }

    $lines | Out-File -FilePath $outFile -Encoding utf8
}

Assert-RepoRoot

$ts = Get-Date -Format "yyyyMMdd-HHmmss"
$slug = @($ts, $Phase) + $(if ($Label.Trim()) { $Label.Trim().Replace(" ","_") } else { @() })
$bundleName = ($slug -join "-")

$outRoot = Join-Path $RepoRoot "artifacts\statecapture\$bundleName"
Assert-SafePath $outRoot

if ($PSCmdlet.ShouldProcess($outRoot, 'Create output bundle directory')) {
    New-Item -ItemType Directory -Path $outRoot -Force | Out-Null
    Write-Verbose "Created output directory: $outRoot"
}

$logFile = Join-Path $outRoot "run.log"
"[$(Get-Date -Format u)] Invoke-BaselineStateCapture starting" | Out-File $logFile -Encoding utf8
"Phase=$Phase Label=$Label" | Add-Content $logFile
"RepoRoot=$RepoRoot" | Add-Content $logFile
"Bundle=$bundleName" | Add-Content $logFile

# --- Capture outputs ---
try {
    $sf = (Join-Path $outRoot "systeminfo.txt")
    if ($PSCmdlet.ShouldProcess($sf, 'Write systeminfo capture')) {
        systeminfo | Out-File $sf -Encoding utf8
        Write-Verbose "Wrote systeminfo to $sf"
    }
} catch { "systeminfo failed: $_" | Add-Content $logFile }

try {
    $ef = (Join-Path $outRoot "env.txt")
    if ($PSCmdlet.ShouldProcess($ef, 'Write env capture')) {
        Get-ChildItem Env: | Sort-Object Name | Out-File $ef -Encoding utf8
        Write-Verbose "Wrote env to $ef"
    }
} catch { "env capture failed: $_" | Add-Content $logFile }

try {
    Get-Process | Sort-Object ProcessName |
        Select-Object ProcessName, Id, CPU, WS, StartTime, Path |
        Export-Csv (Join-Path $outRoot "processes.csv") -NoTypeInformation -Encoding utf8
} catch { "process capture failed: $_" | Add-Content $logFile }

try {
    Get-Service | Sort-Object DisplayName |
        Select-Object Name, DisplayName, Status, StartType |
        Export-Csv (Join-Path $outRoot "services.csv") -NoTypeInformation -Encoding utf8
} catch { "service capture failed: $_" | Add-Content $logFile }

try {
    Get-ScheduledTask |
        Select-Object TaskPath, TaskName, State |
        Sort-Object TaskPath, TaskName |
        Export-Csv (Join-Path $outRoot "scheduledtasks.csv") -NoTypeInformation -Encoding utf8
} catch { "scheduled task capture failed: $_" | Add-Content $logFile }

try {
    Get-NetIPConfiguration |
        Select-Object InterfaceAlias, IPv4Address, IPv6Address, DNSServer, IPv4DefaultGateway |
        Export-Csv (Join-Path $outRoot "netip.csv") -NoTypeInformation -Encoding utf8
} catch { "net ip capture failed: $_" | Add-Content $logFile }

try {
    Get-NetFirewallProfile |
        Select-Object Name, Enabled, DefaultInboundAction, DefaultOutboundAction |
        Out-File (Join-Path $outRoot "firewall_profiles.txt") -Encoding utf8
} catch { "firewall profile capture failed: $_" | Add-Content $logFile }

try {
    $fwExp = (Join-Path $outRoot "firewall_export.wfw")
    if ($PSCmdlet.ShouldProcess($fwExp, 'Export firewall configuration')) {
        netsh advfirewall export $fwExp | Out-Null
        Write-Verbose "Exported firewall to $fwExp"
    }
} catch { "firewall export failed: $_" | Add-Content $logFile }

# --- Manifest ---
$manifest = [ordered]@{
    schema_version = "1.0"
    module = "BaselineStateCapture"
    phase = $Phase
    label = $Label
    timestamp_local = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    timestamp_utc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd HH:mm:ss")
    repo_root = $RepoRoot
    output_dir = $outRoot
}
if ($PSCmdlet.ShouldProcess((Join-Path $outRoot "manifest.json"), 'Write manifest')) {
    $manifest | ConvertTo-Json -Depth 5 | Out-File (Join-Path $outRoot "manifest.json") -Encoding utf8
    Write-Verbose "Wrote manifest.json"
}

# --- Hashes ---
if ($PSCmdlet.ShouldProcess((Join-Path $outRoot "hashes.sha256"), 'Write hashes')) {
    Write-FileHashList -targetDir $outRoot -outFile (Join-Path $outRoot "hashes.sha256")
    Write-Verbose "Wrote hashes.sha256"
}

"[$(Get-Date -Format u)] Completed successfully" | Add-Content $logFile
Write-Output "State capture bundle created: $outRoot"
