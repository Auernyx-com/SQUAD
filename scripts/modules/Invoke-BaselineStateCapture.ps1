[CmdletBinding()]
param(
    [ValidateSet("PRE","POST")]
    [string]$Phase = "PRE",

    [string]$Label = ""
)

$RepoMarker = ".baseline-repo.marker"
$RepoRoot = (Get-Location).Path
$MarkerPath = Join-Path $RepoRoot $RepoMarker

function Throw-Fatal($msg) {
    Write-Error $msg
    exit 1
}

function Assert-RepoRoot {
    if (-not (Test-Path $MarkerPath)) {
        Throw-Fatal "Baseline marker missing. Refusing to run outside a baseline repo root."
    }
}

function Assert-SafePath($path) {
    $full = [System.IO.Path]::GetFullPath($path)
    if (-not $full.StartsWith($RepoRoot)) {
        Throw-Fatal "Path escape detected: $path"
    }
}

function Write-FileHashList($targetDir, $outFile) {
    $items = Get-ChildItem -Path $targetDir -File -Recurse |
        Sort-Object FullName

    $lines = foreach ($f in $items) {
        $h = Get-FileHash -Algorithm SHA256 -Path $f.FullName
        "{0}  {1}" -f $h.Hash, ($h.Path.Substring($RepoRoot.Length + 1))
    }

    $lines | Out-File -FilePath $outFile -Encoding utf8
}

Assert-RepoRoot

$ts = Get-Date -Format "yyyyMMdd-HHmmss"
$slug = @($ts, $Phase) + $(if ($Label.Trim()) { $Label.Trim().Replace(" ","_") } else { @() })
$bundleName = ($slug -join "-")

$outRoot = Join-Path $RepoRoot "artifacts\statecapture\$bundleName"
Assert-SafePath $outRoot

New-Item -ItemType Directory -Path $outRoot -Force | Out-Null

$logFile = Join-Path $outRoot "run.log"
"[$(Get-Date -Format u)] Invoke-BaselineStateCapture starting" | Out-File $logFile -Encoding utf8
"Phase=$Phase Label=$Label" | Add-Content $logFile
"RepoRoot=$RepoRoot" | Add-Content $logFile
"Bundle=$bundleName" | Add-Content $logFile

# --- Capture outputs ---
try {
    systeminfo | Out-File (Join-Path $outRoot "systeminfo.txt") -Encoding utf8
} catch { "systeminfo failed: $_" | Add-Content $logFile }

try {
    Get-ChildItem Env: | Sort-Object Name | Out-File (Join-Path $outRoot "env.txt") -Encoding utf8
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
    netsh advfirewall export (Join-Path $outRoot "firewall_export.wfw") | Out-Null
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
$manifest | ConvertTo-Json -Depth 5 | Out-File (Join-Path $outRoot "manifest.json") -Encoding utf8

# --- Hashes ---
Write-FileHashList -targetDir $outRoot -outFile (Join-Path $outRoot "hashes.sha256")

"[$(Get-Date -Format u)] Completed successfully" | Add-Content $logFile
Write-Host "State capture bundle created: $outRoot"
