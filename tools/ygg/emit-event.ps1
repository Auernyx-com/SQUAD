<#
Yggdrasil Canon Event Emitter (Level 1)
- Builds a canonical payload (minified JSON, UTF-8)
- Computes sha256 digest over the canonical payload bytes
- Wraps into an envelope with canonical_event_id, parser_version, digest
- Optionally writes envelope to disk (queue folder)
- Optionally invokes an agent command with the envelope (stdin or temp file)

Usage examples:
  # Just print envelope (default)
  .\tools\ygg\emit-event.ps1 -Intent baseline_pre_check -Repo auernyx-agent

  # Write envelope to canon queue folder
  .\tools\ygg\emit-event.ps1 -Intent baseline_pre_check -Repo auernyx-agent -Write

  # Invoke your agent command (replace with your real runner)
  .\tools\ygg\emit-event.ps1 -Intent baseline_pre_check -Repo auernyx-agent -Invoke `
    -AgentCommand "python .\auernyx_agent.py --input -" -UseStdin

  # Invoke via temp file
  .\tools\ygg\emit-event.ps1 -Intent baseline_pre_check -Repo auernyx-agent -Invoke `
    -AgentCommand "python .\auernyx_agent.py --input-file" -UseFile
#>

[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)]
  [ValidateNotNullOrEmpty()]
  [string]$Intent,

  [Parameter(Mandatory=$true)]
  [ValidateNotNullOrEmpty()]
  [string]$Repo,

  [Parameter()]
  [ValidateSet("dry-run","run")]
  [string]$Mode = "dry-run",

  [Parameter()]
  [string]$BranchId = "auernyx-agent",

  [Parameter()]
  [string]$ParserVersion = "yggdrasil-parser@1.0.0",

  # Optional extra fields for your payload (key=value pairs)
  [Parameter()]
  [string[]]$ParamKV = @(),

  # If set: write envelope JSON to canon queue folder
  [switch]$Write,

  # If set: recompute digest from canonical_payload_json and assert match before any invoke
  [switch]$CanonVerify,

  # If set: also invoke the agent
  [switch]$Invoke,

  # How to deliver envelope to agent
  [switch]$UseStdin,
  [switch]$UseFile,

  # The agent command to run. You control this.
  # Examples:
  #   "python .\auernyx_agent.py --input -"
  #   "node .\src\cli.js --event -"
  [Parameter()]
  [string]$AgentCommand = "",

  # Where to write canon queue events (only used if -Write)
  [Parameter()]
  [string]$CanonQueueDir = ".\canon\queue"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-TimestampUtcCompact {
  return (Get-Date).ToUniversalTime().ToString("yyyyMMdd_HHmmss")
}

function Slugify([string]$s) {
  $t = $s.ToLowerInvariant()
  $t = $t -replace '[^a-z0-9]+','_'
  $t = $t.Trim('_')
  if ([string]::IsNullOrWhiteSpace($t)) { return "event" }
  return $t
}

function Parse-KV([string[]]$pairs) {
  $ht = @{}
  foreach ($p in $pairs) {
    if ([string]::IsNullOrWhiteSpace($p)) { continue }
    $idx = $p.IndexOf("=")
    if ($idx -lt 1) {
      throw "Invalid -ParamKV entry '$p'. Use key=value."
    }
    $k = $p.Substring(0, $idx).Trim()
    $vRaw = $p.Substring($idx + 1).Trim()

    if ([string]::IsNullOrWhiteSpace($k)) {
      throw "Invalid -ParamKV entry '$p' (empty key)."
    }

    $v = $vRaw
    if ($vRaw -match '^(true|false)$') {
      $v = [bool]::Parse($vRaw)
    } elseif ($vRaw -match '^null$') {
      $v = $null
    } elseif ($vRaw -match '^-?\d+$') {
      $v = [int64]$vRaw
    } elseif ($vRaw -match '^-?\d+\.\d+$') {
      $v = [double]$vRaw
    } elseif (($vRaw.StartsWith("{") -and $vRaw.EndsWith("}")) -or ($vRaw.StartsWith("[") -and $vRaw.EndsWith("]"))) {
      try {
        $v = $vRaw | ConvertFrom-Json -ErrorAction Stop
      } catch {
        $v = $vRaw
      }
    }

    $ht[$k] = $v
  }
  return $ht
}

function Canonicalize-Json([object]$obj) {
  return ($obj | ConvertTo-Json -Depth 100 -Compress)
}

function Sha256HexOfUtf8([string]$text) {
  $bytes = [System.Text.Encoding]::UTF8.GetBytes($text)
  $sha256 = [System.Security.Cryptography.SHA256]::Create()
  try {
    $hashBytes = $sha256.ComputeHash($bytes)
  } finally {
    $sha256.Dispose()
  }
  return (($hashBytes | ForEach-Object { $_.ToString("x2") }) -join "")
}

$extraParams = Parse-KV $ParamKV

$payload = [ordered]@{
  intent = $Intent
  parameters = [ordered]@{
    repo = $Repo
    mode = $Mode
  }
}

foreach ($k in $extraParams.Keys) {
  $payload.parameters[$k] = $extraParams[$k]
}

$payloadJson = Canonicalize-Json $payload
$payloadHash = Sha256HexOfUtf8 $payloadJson
$digest = "sha256:$payloadHash"

$ts = Get-TimestampUtcCompact
$slug = Slugify "$Intent"
$canonicalEventId = "EVT_${ts}_${slug}"

$envelope = [ordered]@{
  branch_id = $BranchId
  canonical_event_id = $canonicalEventId
  parser_version = $ParserVersion
  canonical_payload_digest = $digest
  # Canonical payload bytes used for digest (Level 1 law): UTF-8 (no BOM) of this exact string.
  canonical_payload_json = $payloadJson
  canonical_payload = ($payloadJson | ConvertFrom-Json)
}

$envelopeJson = Canonicalize-Json $envelope

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

if ($CanonVerify) {
  $recomputed = "sha256:" + (Sha256HexOfUtf8 $payloadJson)
  if ($recomputed -ne $digest) {
    throw ("CanonVerify failed: recomputed digest mismatch. Expected={0} Got={1}" -f $digest, $recomputed)
  }
}

Write-Output $envelopeJson

$writtenPath = $null
if ($Write) {
  if (-not (Test-Path -LiteralPath $CanonQueueDir)) {
    New-Item -ItemType Directory -Path $CanonQueueDir | Out-Null
  }

  $filename = "${canonicalEventId}.json"
  $writtenPath = Join-Path $CanonQueueDir $filename
  [System.IO.File]::WriteAllText($writtenPath, $envelopeJson, $utf8NoBom)
}

if ($Invoke) {
  if ([string]::IsNullOrWhiteSpace($AgentCommand)) {
    throw "You set -Invoke but did not provide -AgentCommand."
  }

  if (-not $UseStdin -and -not $UseFile) {
    $UseStdin = $true
  }

  if ($UseStdin) {
    # Byte-clean stdin delivery: write to a temp file (UTF-8 no BOM) and let cmd.exe redirect it.
    # This avoids PowerShell object pipeline transformations.
    $tmpIn = Join-Path $env:TEMP "${canonicalEventId}_stdin.json"
    [System.IO.File]::WriteAllText($tmpIn, $envelopeJson, $utf8NoBom)
    try {
      # cmd.exe quoting rule: wrap the whole command in quotes, and use doubled-quotes inside.
      # Example: /c "python agent.py --input - < ""C:\path\stdin.json"""
      $cmdArgs = '/c "' + $AgentCommand + ' < ""' + $tmpIn + '"""'
      & cmd.exe $cmdArgs
      exit $LASTEXITCODE
    } finally {
      if (Test-Path -LiteralPath $tmpIn) { Remove-Item -LiteralPath $tmpIn -Force -ErrorAction SilentlyContinue }
    }
  }

  if ($UseFile) {
    $tmp = Join-Path $env:TEMP "${canonicalEventId}_envelope.json"
    [System.IO.File]::WriteAllText($tmp, $envelopeJson, $utf8NoBom)
    try {
      # Avoid nested PowerShell -Command quoting pitfalls; run the provided command line
      # and append the temp path as a single, quoted argument.
      $cmdLine = "$AgentCommand `"$tmp`""
      Invoke-Expression $cmdLine
    } finally {
      if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }
    }
  }
}
