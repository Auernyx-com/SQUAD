<#
.SYNOPSIS
  SOCIALOPS v1 (Draft + Queue Generator) — governed social drafting.

.DESCRIPTION
  Draft → Preview → Approve(APPLY) → Export.

  - Reads one provided source file (text/markdown).
  - Loads account policy from SOCIAL/policy.*.json
  - Generates drafts and prints a preview including which source lines were used.
  - Writes artifacts ONLY when -Confirm APPLY is provided.
  - Never posts, replies, or uses cloud/APIs.

  Contract (one sentence):
    Generates drafts and schedules from provided sources under policy constraints,
    but may not publish, reply, or invent claims.
#>

[CmdletBinding()]
param(
  # Source text file (recommended: keep in SOCIAL/SOURCES)
  [Parameter(Mandatory=$true)]
  [string]$SourcePath,

  # Account voice (policy-driven)
  [Parameter(Mandatory=$true)]
  [ValidateSet('SQUAD','AUERNYX')]
  [string]$Account,

  # Target platform (policy may support multiple platforms; currently used for headers + filenames)
  [Parameter(Mandatory=$false)]
  [ValidateSet('x','linkedin','facebook','instagram','reddit')]
  [string]$Platform = 'x',

  # Generation intent
  [Parameter(Mandatory=$false)]
  [ValidateSet('X_DRAFTS','THREAD','REWRITE_NEUTRAL','BULLETS_TO_POST')]
  [string]$Mode = 'X_DRAFTS',

  # Draft count (for X_DRAFTS)
  [Parameter(Mandatory=$false)]
  [ValidateRange(1,20)]
  [int]$Count = 5,

  # Optional input post (for REWRITE_NEUTRAL)
  [Parameter(Mandatory=$false)]
  [string]$InputPost,

  # Governed flow control
  # - PREVIEW: drafts+receipts are written; queue export is blocked.
  # - APPLY: queue export is allowed (but blocked if policy checks fail).
  [Parameter(Mandatory=$false)]
  [string]$Confirm = 'PREVIEW',

  # Export a scheduler-ready queue artifact on APPLY
  [Parameter(Mandatory=$false)]
  [switch]$ExportQueue = $true,

  # Queue month (YYYY-MM). Default: current month. Used for queue filename.
  [Parameter(Mandatory=$false)]
  [ValidatePattern('^\d{4}-\d{2}$')]
  [string]$QueueMonth = $(Get-Date -Format 'yyyy-MM'),

  # Optional schedule date for queue rows (YYYY-MM-DD). Blank means unscheduled.
  [Parameter(Mandatory=$false)]
  [ValidatePattern('^\d{4}-\d{2}-\d{2}$')]
  [string]$ScheduleDate,

  # Optional schedule time for queue rows (HH:MM 24h). Blank means unscheduled.
  [Parameter(Mandatory=$false)]
  [ValidatePattern('^\d{2}:\d{2}$')]
  [string]$ScheduleTime
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

trap {
  Write-Host ''
  Write-Host '=== SOCIALOPS ERROR ==='
  try {
    Write-Host ("Message: {0}" -f $_.Exception.Message)
    if ($_.InvocationInfo -and $_.InvocationInfo.PositionMessage) {
      Write-Host '---'
      Write-Host $_.InvocationInfo.PositionMessage
    }
    if ($_.ScriptStackTrace) {
      Write-Host '---'
      Write-Host $_.ScriptStackTrace
    }
  } catch {
    Write-Host 'Unhandled error (failed to render details).'
  }
  exit 1
}

function Resolve-RepoRoot {
  # Script is intended to live in repo root.
  return (Resolve-Path -LiteralPath $PSScriptRoot).Path
}

function Read-Json([string]$Path) {
  $raw = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
  return ($raw | ConvertFrom-Json)
}

function Try-GetProp($obj, [string]$name, $default = $null) {
  if ($null -eq $obj) { return $default }
  $p = $obj.PSObject.Properties[$name]
  if ($null -eq $p) { return $default }
  return $p.Value
}

function Get-PolicyPath([string]$Root, [string]$Account) {
  switch ($Account) {
    'SQUAD' { return (Join-Path $Root 'SOCIAL\policy.squad.json') }
    'AUERNYX' { return (Join-Path $Root 'SOCIAL\policy.auernyx.json') }
    default { throw "Unsupported account: $Account" }
  }
}

function Normalize-Whitespace([string]$s) {
  if ($null -eq $s) { return '' }
  return ($s -replace "\s+", ' ').Trim()
}

function Get-SourceLines([string]$Path) {
  $lines = Get-Content -LiteralPath $Path -Encoding UTF8
  $out = New-Object System.Collections.Generic.List[object]
  for ($i = 0; $i -lt $lines.Count; $i++) {
    $text = [string]$lines[$i]
    $trim = $text.Trim()
    if (-not $trim) { continue }
    # Skip very long code-ish lines to keep posts readable.
    if ($trim.Length -gt 240) { continue }
    $out.Add([pscustomobject]@{ line = ($i + 1); text = $trim })
  }
  return ,$out
}

function Select-AnchorLines($sourceLines, [int]$maxItems) {
  # Deterministic selection: first N meaningful lines.
  $picked = @()
  foreach ($x in $sourceLines) {
    if ($picked.Count -ge $maxItems) { break }
    $picked += $x
  }
  return ,$picked
}

function Enforce-MaxLen([string]$text, [int]$max) {
  $t = Normalize-Whitespace $text
  if ($t.Length -le $max) { return $t }
  # Hard-trim (no ellipsis claims).
  return $t.Substring(0, $max).TrimEnd()
}

function Get-MaxCharsX($policy) {
  return (Get-MaxCharsForPlatform -policy $policy -platform 'x')
}

function Get-PlatformLimits($policy, [string]$platform) {
  $p = ([string]$platform).Trim().ToLowerInvariant()
  $limits = Try-GetProp $policy 'limits' $null
  if ($null -eq $limits) { return $null }

  $byPlatform = Try-GetProp $limits 'by_platform' $null
  if ($null -ne $byPlatform) {
    $pObj = Try-GetProp $byPlatform $p $null
    if ($null -ne $pObj) { return $pObj }
  }

  return $null
}

function Get-MaxCharsForPlatform($policy, [string]$platform) {
  $p = ([string]$platform).Trim().ToLowerInvariant()
  $pLimits = Get-PlatformLimits -policy $policy -platform $p
  $pMax = Try-GetProp $pLimits 'max_chars' $null
  if ($null -ne $pMax) { return [int]$pMax }

  $limits = Try-GetProp $policy 'limits' $null
  if ($p -eq 'x') {
    $maxCharsX = Try-GetProp $limits 'max_chars_x' $null
    if ($null -ne $maxCharsX) { return [int]$maxCharsX }
  }

  $format = Try-GetProp $policy 'format' $null
  $legacy = Try-GetProp $format 'max_chars_per_post' $null
  if ($null -ne $legacy) { return [int]$legacy }

  # Conservative fallback
  return 280
}

function Get-MaxHashtagsForPlatform($policy, [string]$platform) {
  $p = ([string]$platform).Trim().ToLowerInvariant()
  $pLimits = Get-PlatformLimits -policy $policy -platform $p
  $pMax = Try-GetProp $pLimits 'max_hashtags' $null
  if ($null -ne $pMax) { return [int]$pMax }

  $limits = Try-GetProp $policy 'limits' $null
  $maxHash = Try-GetProp $limits 'max_hashtags' $null
  if ($null -ne $maxHash) { return [int]$maxHash }

  $hashtagsObj = Try-GetProp $policy 'hashtags' $null
  $legacyHash = Try-GetProp $hashtagsObj 'max' $null
  if ($null -ne $legacyHash) { return [int]$legacyHash }

  return 2
}

function Get-MaxEmojisForPlatform($policy, [string]$platform) {
  $p = ([string]$platform).Trim().ToLowerInvariant()
  $pLimits = Get-PlatformLimits -policy $policy -platform $p
  $pMax = Try-GetProp $pLimits 'max_emojis' $null
  if ($null -ne $pMax) { return [int]$pMax }

  $limits = Try-GetProp $policy 'limits' $null
  $maxE = Try-GetProp $limits 'max_emojis' $null
  if ($null -ne $maxE) { return [int]$maxE }

  return $null
}

function Get-ThreadConfig($policy) {
  # Prefer per-platform thread config if present (x is the common case)
  $xLimits = Get-PlatformLimits -policy $policy -platform 'x'
  $t0 = Try-GetProp $xLimits 'thread' $null
  if ($null -ne $t0) { return $t0 }

  $limits = Try-GetProp $policy 'limits' $null
  $t1 = Try-GetProp $limits 'thread' $null
  if ($null -ne $t1) { return $t1 }

  $format = Try-GetProp $policy 'format' $null
  $t2 = Try-GetProp $format 'thread' $null
  if ($null -ne $t2) { return $t2 }

  return $null
}

function Count-Hashtags([string]$text) {
  $m = [regex]::Matches($text, '(?<!\w)#\w+')
  return $m.Count
}

function Count-Emojis([string]$text) {
  if ([string]::IsNullOrWhiteSpace($text)) { return 0 }
  # Heuristic emoji detector (covers common emoji ranges) without regex \x{...}
  # because Windows PowerShell 5.1 runs on .NET Framework regex.
  $count = 0
  $e = [System.Globalization.StringInfo]::GetTextElementEnumerator($text)
  while ($e.MoveNext()) {
    $elem = [string]$e.Current
    if (-not $elem) { continue }

    $cp = 0
    if ($elem.Length -ge 2 -and [char]::IsHighSurrogate($elem[0]) -and [char]::IsLowSurrogate($elem[1])) {
      $cp = [char]::ConvertToUtf32($elem, 0)
    } else {
      $cp = [int][char]$elem[0]
    }

    if (
      ($cp -ge 0x1F300 -and $cp -le 0x1FAFF) -or
      ($cp -ge 0x2600 -and $cp -le 0x26FF) -or
      ($cp -ge 0x2700 -and $cp -le 0x27BF)
    ) {
      $count++
    }
  }
  return $count
}

function Find-BannedMatches([string]$text, [string[]]$banned) {
  $hits = New-Object System.Collections.Generic.List[string]
  foreach ($p in ($banned | Where-Object { $_ -and $_.Trim() })) {
    if ($text.ToLowerInvariant().Contains($p.ToLowerInvariant())) {
      $hits.Add($p)
    }
  }
  return ,$hits
}

function Find-BannedMatchesWithEvidence($sources, [string[]]$banned) {
  # Returns: @{
  #   hits = @('phrase1', ...)
  #   evidence = @(@{ phrase='...'; line=12; text='...' }, ...)
  # }
  $hits = New-Object System.Collections.Generic.List[string]
  $evidence = New-Object System.Collections.Generic.List[object]

  if (-not $sources) {
    return [pscustomobject]@{ hits = @(); evidence = @() }
  }

  foreach ($s in $sources) {
    $lineText = [string]$s.text
    foreach ($p in ($banned | Where-Object { $_ -and $_.Trim() })) {
      if ($lineText.ToLowerInvariant().Contains($p.ToLowerInvariant())) {
        $hits.Add($p)
        $evidence.Add([pscustomobject]@{ phrase = $p; line = $s.line; text = $s.text })
      }
    }
  }

  $uniqHits = @($hits | Select-Object -Unique)
  return [pscustomobject]@{
    hits = @($uniqHits)
    evidence = @($evidence.ToArray())
  }
}

function Build-Header(
  [string]$Account,
  [string]$Platform,
  [string[]]$SourceFiles,
  [string]$SourceSha256,
  [string[]]$ClaimsUsed,
  [string]$BannedCheck,
  [string]$PolicyPath,
  [string]$PolicySha256,
  $BannedEvidence
) {
  function YamlSingleQuote([string]$v) {
    if ($null -eq $v) { $v = '' }
    return "'" + ($v -replace "'", "''") + "'"
  }

  function YamlDoubleQuote([string]$v) {
    if ($null -eq $v) { $v = '' }
    $escaped = $v -replace '"', '\\"'
    return '"' + $escaped + '"'
  }

  function YamlScalar([string]$v) {
    # Prefer plain scalars for audit friendliness; quote only when needed.
    if ($null -eq $v) { return "''" }
    $t = [string]$v
    if ($t -match '[\s:#\[\]\{\},&\*\?\|\-<>=!%@\\]') {
      return (YamlSingleQuote $t)
    }
    return $t
  }

  $srcLines = @('source_files:')
  foreach ($s in $SourceFiles) {
    $srcLines += ("  - " + (YamlScalar $s))
  }

  $claimLines = @('claims_used:')
  foreach ($c in ($ClaimsUsed | Where-Object { $_ -and $_.Trim() })) {
    $claimLines += ("  - " + (YamlDoubleQuote $c))
  }
  if ($claimLines.Count -eq 1) { $claimLines += "  - ''" }

  $hdr = New-Object System.Collections.Generic.List[string]
  $hdr.Add('---')
  $hdr.Add("account: $Account")
  $hdr.Add("platform: $Platform")
  foreach ($l in $srcLines) { $hdr.Add($l) }
  if (-not [string]::IsNullOrWhiteSpace($SourceSha256)) {
    $hdr.Add(("source_sha256: {0}" -f $SourceSha256))
  }
  $hdr.Add(("policy: {0}" -f $PolicyPath))
  if (-not [string]::IsNullOrWhiteSpace($PolicySha256)) {
    $hdr.Add(("policy_sha256: {0}" -f $PolicySha256))
  }
  foreach ($l in $claimLines) { $hdr.Add($l) }
  $hdr.Add("banned_check: $BannedCheck")

  if ($BannedCheck -ne 'PASS' -and $BannedEvidence -and $BannedEvidence.Count -gt 0) {
    $hdr.Add('banned_evidence:')
    foreach ($e in $BannedEvidence) {
      $hdr.Add(("  - phrase: " + (YamlSingleQuote ([string]$e.phrase))))
      $hdr.Add(("    line: {0}" -f $e.line))
      $hdr.Add(("    text: " + (YamlSingleQuote ([string]$e.text))))
    }
  }

  $hdr.Add('---')
  $hdr.Add('')
  return ($hdr -join "`n")
}

function Build-XDrafts($policy, $anchorLines, [int]$count) {
  $max = Get-MaxCharsForPlatform -policy $policy -platform $Platform
  $drafts = New-Object System.Collections.Generic.List[object]

  if ($anchorLines.Count -eq 0) {
    throw 'Source has no usable lines to draft from.'
  }

  for ($i = 0; $i -lt $count; $i++) {
    # Rotate through anchor lines deterministically.
    $a = $anchorLines[$i % $anchorLines.Count]
    $b = $anchorLines[($i + 1) % $anchorLines.Count]

    $body = "Update: $($a.text)"
    if ($b.line -ne $a.line) {
      $body = $body + " | " + $b.text
    }

    $post = Enforce-MaxLen $body $max

    $drafts.Add([pscustomobject]@{
      kind = 'X'
      text = $post
      sources = @($a, $b | Where-Object { $_.line -ne $a.line })
    })
  }

  return ,$drafts
}

function Build-Thread($policy, $anchorLines) {
  $threadCfg = Get-ThreadConfig $policy
  if (-not $threadCfg) {
    throw 'Thread format is not configured in policy (expected policy.limits.thread.* or policy.format.thread.*).'
  }

  $max = 280
  $tMaxLegacy = Try-GetProp $threadCfg 'max_chars_per_post' $null
  $tMax = Try-GetProp $threadCfg 'max_chars' $null
  $tMaxX = Try-GetProp $threadCfg 'max_chars_x' $null
  if ($null -ne $tMaxLegacy) {
    $max = [int]$tMaxLegacy
  } elseif ($null -ne $tMax) {
    $max = [int]$tMax
  } elseif ($null -ne $tMaxX) {
    $max = [int]$tMaxX
  }

  $maxPosts = 8
  $tPosts = Try-GetProp $threadCfg 'max_posts' $null
  if ($null -ne $tPosts) { $maxPosts = [int]$tPosts }

  if ($anchorLines.Count -eq 0) {
    throw 'Source has no usable lines to draft from.'
  }

  $posts = New-Object System.Collections.Generic.List[object]

  # Thread structure: intro + 1-6 factual bullets from source.
  $intro = Enforce-MaxLen "Release note summary (technical): $($anchorLines[0].text)" $max
  $posts.Add([pscustomobject]@{ text = $intro; sources = @($anchorLines[0]) })

  $idx = 1
  while ($posts.Count -lt $maxPosts -and $idx -lt $anchorLines.Count) {
    $line = $anchorLines[$idx]
    $t = Enforce-MaxLen ("- " + $line.text) $max
    $posts.Add([pscustomobject]@{ text = $t; sources = @($line) })
    $idx++
  }

  return ,$posts
}

function Rewrite-Neutral($policy, [string]$inputText) {
  if ([string]::IsNullOrWhiteSpace($inputText)) {
    throw 'REWRITE_NEUTRAL requires -InputPost.'
  }

  $max = Get-MaxCharsForPlatform -policy $policy -platform $Platform
  $t = Normalize-Whitespace $inputText

  # Minimal neutralizer: remove obvious hype words and exclamation density.
  $t = $t -replace '(!){2,}', '!'
  $t = $t -replace '(?i)\b(amazing|incredible|life\-changing|revolutionary|game\-changing|unbelievable)\b', 'notable'
  $t = $t -replace '(?i)\b(definitely|guaranteed|always)\b', 'often'

  $t = Enforce-MaxLen $t $max

  return [pscustomobject]@{
    kind = 'X'
    text = $t
    sources = @()  # rewrite mode is not line-anchored to a file
  }
}

function Bullets-To-Post($policy, $anchorLines) {
  $max = Get-MaxCharsForPlatform -policy $policy -platform $Platform
  if ($anchorLines.Count -eq 0) { throw 'Source has no usable lines.' }

  $bullets = $anchorLines | Select-Object -First 3
  $body = "Facts: " + (($bullets | ForEach-Object { $_.text }) -join ' | ')
  $post = Enforce-MaxLen $body $max

  return [pscustomobject]@{ kind = 'X'; text = $post; sources = $bullets }
}

function Ensure-Dir([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path)) {
    New-Item -ItemType Directory -Path $Path -Force | Out-Null
  }
}

function Write-Utf8([string]$Path, [string]$Text) {
  $Text | Out-File -LiteralPath $Path -Encoding utf8 -Force
}

function Sha256([string]$Path) {
  return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Try-FileSha256([string]$Path) {
  # Best-effort hashing: do not fail generation if hashing is unavailable.
  try {
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
  } catch {
    return $null
  }
}

# --------------------
# Main
# --------------------

$root = Resolve-RepoRoot
$resolvedSource = (Resolve-Path -LiteralPath $SourcePath).Path

$confirmNorm = ([string]$Confirm).Trim().ToUpperInvariant()
if ($confirmNorm -eq 'APPLY') { $confirmNorm = 'APPLY' }
elseif ($confirmNorm -eq 'PREVIEW' -or -not $confirmNorm) { $confirmNorm = 'PREVIEW' }
else { throw "Invalid -Confirm value: $Confirm (use PREVIEW or APPLY)" }

if (-not (Test-Path -LiteralPath $resolvedSource)) {
  throw "Source file not found: $resolvedSource"
}

$policyPath = Get-PolicyPath -Root $root -Account $Account
if (-not (Test-Path -LiteralPath $policyPath)) {
  throw "Policy file not found: $policyPath"
}

$policy = Read-Json $policyPath

# Basic refusal triggers (explicit, deterministic)
# NOTE: This is governance/QA only. It cannot detect all unsafe requests.
$refusalTerms = @(
  'invent', 'make up', 'pretend', 'published', 'scheduled',
  'partnership', 'official', 'endorsement',
  'diagnose', 'treatment', 'prescribe'
)

$sourceRaw = Get-Content -LiteralPath $resolvedSource -Raw -Encoding UTF8
foreach ($term in $refusalTerms) {
  if ($sourceRaw.ToLowerInvariant().Contains($term)) {
    # This is conservative: if the source itself contains these terms, we do NOT refuse.
    # Refusals are for user instructions, not source content.
    continue
  }
}

$sourceLines = Get-SourceLines $resolvedSource
$anchor = Select-AnchorLines -sourceLines $sourceLines -maxItems 12

$today = Get-Date -Format 'yyyy-MM-dd'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'

# Generate drafts/posts
$bundle = @()
$bundleKind = ''

switch ($Mode) {
  'X_DRAFTS' {
    if ($Account -ne 'SQUAD' -and $Account -ne 'AUERNYX') { throw 'Invalid account.' }
    $bundle = Build-XDrafts -policy $policy -anchorLines $anchor -count $Count
    $bundleKind = 'x'
  }
  'THREAD' {
    if ($Account -ne 'AUERNYX') {
      throw 'THREAD mode is AUERNYX-only (technical thread policy).'
    }
    $bundle = Build-Thread -policy $policy -anchorLines $anchor
    $bundleKind = 'thread'
  }
  'REWRITE_NEUTRAL' {
    $bundle = @(Rewrite-Neutral -policy $policy -inputText $InputPost)
    $bundleKind = 'x'
  }
  'BULLETS_TO_POST' {
    $bundle = @(Bullets-To-Post -policy $policy -anchorLines $anchor)
    $bundleKind = 'x'
  }
  default {
    throw "Unsupported mode: $Mode"
  }
}

# Policy checks
$maxHashtags = Get-MaxHashtagsForPlatform -policy $policy -platform $Platform
$maxEmojis = Get-MaxEmojisForPlatform -policy $policy -platform $Platform

$banned = @()
$toneObj = Try-GetProp $policy 'tone' $null
$toneBanned = Try-GetProp $toneObj 'banned_phrases' $null
if ($toneBanned) { $banned += @($toneBanned) }

$topBanned = Try-GetProp $policy 'banned_phrases' $null
if ($topBanned) { $banned += @($topBanned) }
$banned = @($banned | Where-Object { $_ -and $_.Trim() } | Select-Object -Unique)

$previewItems = New-Object System.Collections.Generic.List[object]

# Claims used (tiny, audit-friendly)
$claimsUsed = @()
if ($Mode -eq 'THREAD') { $claimsUsed = @('Release notes summary') }
elseif ($Mode -eq 'BULLETS_TO_POST') { $claimsUsed = @('Release notes summary') }
elseif ($Mode -eq 'REWRITE_NEUTRAL') { $claimsUsed = @('Governance constraints and refusal rules') }
else { $claimsUsed = @('This update adds <feature>.') }

for ($i = 0; $i -lt $bundle.Count; $i++) {
  $item = $bundle[$i]
  $text = [string]$item.text

  $srcEvidence = Find-BannedMatchesWithEvidence -sources $item.sources -banned $banned
  $hits = @($srcEvidence.hits)
  $hashtagCount = Count-Hashtags -text $text

  $emojiCount = Count-Emojis -text $text

  $hashtagOk = ($hashtagCount -le $maxHashtags)
  $emojiOk = $(if ($null -eq $maxEmojis) { $true } else { $emojiCount -le $maxEmojis })
  $bannedPass = ($hits.Count -eq 0)

  $previewItems.Add([pscustomobject]@{
    index = ($i + 1)
    text = $text
    sources = $item.sources
    hashtag_ok = $hashtagOk
    hashtag_count = $hashtagCount
    emoji_ok = $emojiOk
    emoji_count = $emojiCount
    banned_pass = $bannedPass
    banned_hits = $hits
    banned_evidence = @($srcEvidence.evidence)
  })
}

# Write drafts + receipts (safe) always
$repoRoot = $root
$socialRoot = Join-Path $repoRoot 'SOCIAL'
$draftsDir = Join-Path $socialRoot 'DRAFTS'
$queueDir = Join-Path $socialRoot 'QUEUE'
$receiptsDir = Join-Path $socialRoot 'RECEIPTS'
Ensure-Dir $draftsDir
Ensure-Dir $queueDir
Ensure-Dir $receiptsDir

$sourceHash = Try-FileSha256 -Path $resolvedSource
$policyHash = Try-FileSha256 -Path $policyPath

$writtenDrafts = New-Object System.Collections.Generic.List[object]

for ($i = 0; $i -lt $previewItems.Count; $i++) {
  $p = $previewItems[$i]
  $n = '{0:D3}' -f ($i + 1)

  $draftId = "{0}_{1}_{2}_{3}" -f $today, ($Account.ToLowerInvariant()), ($Platform.ToLowerInvariant()), $n
  $draftPath = Join-Path $draftsDir ("{0}.md" -f $draftId)
  $receiptPath = Join-Path $receiptsDir ("{0}_receipt.json" -f $draftId)

  $bannedCheck = $(if ($p.banned_pass -and $p.hashtag_ok -and $p.emoji_ok) { 'PASS' } else { 'FAIL' })

  # Build workspace-relative source file path for header
  $relSource = $resolvedSource
  if ($relSource.StartsWith($repoRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    $relSource = $relSource.Substring($repoRoot.Length).TrimStart('\\') -replace '\\','/'
  }
  $policyRel = $policyPath
  if ($policyRel.StartsWith($repoRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    $policyRel = $policyRel.Substring($repoRoot.Length).TrimStart('\\') -replace '\\','/'
  }

  $header = Build-Header -Account $Account -Platform $Platform -SourceFiles @($relSource) -SourceSha256 $sourceHash -ClaimsUsed $claimsUsed -BannedCheck $bannedCheck -PolicyPath $policyRel -PolicySha256 $policyHash -BannedEvidence $p.banned_evidence
  $content = $header + $p.text + "`n"
  Write-Utf8 -Path $draftPath -Text $content

  $draftHash = (Get-FileHash -LiteralPath $draftPath -Algorithm SHA256).Hash.ToLowerInvariant()

  $receipt = [ordered]@{
    module = 'SOCIALOPS_v1'
    timestamp = (Get-Date).ToString('o')
    account = $Account
    platform = $Platform
    mode = $Mode
    confirm = $confirmNorm
    source = @{ path = $relSource; sha256 = $sourceHash }
    policy = @{ path = $policyRel; sha256 = $policyHash }
    draft = @{ path = ("SOCIAL/DRAFTS/{0}.md" -f $draftId); sha256 = $draftHash }
    checks = @{
      banned_check = $bannedCheck
      banned_hits = @($p.banned_hits)
      hashtag_count = $p.hashtag_count
      hashtag_max = $maxHashtags
      emoji_count = $p.emoji_count
      emoji_max = $maxEmojis
    }
    sources_used = @(
      @($p.sources | ForEach-Object { [ordered]@{ line = $_.line; text = $_.text } })
    )
    banned_evidence = @(
      @($p.banned_evidence | ForEach-Object { [ordered]@{ phrase = $_.phrase; line = $_.line; text = $_.text } })
    )
  }

  Write-Utf8 -Path $receiptPath -Text (($receipt | ConvertTo-Json -Depth 10) + "`n")

  $writtenDrafts.Add([pscustomobject]@{ draftPath = $draftPath; receiptPath = $receiptPath; bannedCheck = $bannedCheck })
}

# Preview (always)
Write-Host ''
Write-Host '=== SOCIALOPS PREVIEW ==='
Write-Host ("Account:  {0}" -f $Account)
Write-Host ("Platform: {0}" -f $Platform)
Write-Host ("Mode:     {0}" -f $Mode)
Write-Host ("Source:   {0}" -f $resolvedSource)
Write-Host ("Policy:   {0}" -f $policyPath)
Write-Host ("Confirm:  {0}" -f $confirmNorm)
Write-Host ''

foreach ($p in $previewItems) {
  Write-Host ('---')
  Write-Host ("Post #{0}" -f $p.index)
  Write-Host $p.text
  Write-Host ("Hashtags: {0} (max {1}) :: {2}" -f $p.hashtag_count, $maxHashtags, $(if ($p.hashtag_ok) { 'OK' } else { 'FAIL' }))
  if ($null -ne $maxEmojis) {
    Write-Host ("Emojis:   {0} (max {1}) :: {2}" -f $p.emoji_count, $maxEmojis, $(if ($p.emoji_ok) { 'OK' } else { 'FAIL' }))
  }

  if (-not $p.banned_pass -and $p.banned_evidence -and $p.banned_evidence.Count -gt 0) {
    Write-Host 'Banned evidence:'
    foreach ($e in ($p.banned_evidence | Select-Object -First 6)) {
      Write-Host ("  phrase='{0}' at L{1}: {2}" -f $e.phrase, $e.line, $e.text)
    }
  }
  Write-Host ("Banned:   {0}" -f $(if ($p.banned_pass) { 'PASS' } else { 'FAIL: ' + ($p.banned_hits -join ', ') }))

  if ($p.sources -and $p.sources.Count -gt 0) {
    Write-Host 'Sources used:'
    foreach ($s in $p.sources) {
      Write-Host ("  L{0}: {1}" -f $s.line, $s.text)
    }
  } else {
    Write-Host 'Sources used: (none / not line-anchored)'
  }

  Write-Host ''
}


if ($confirmNorm -ne 'APPLY') {
  Write-Host 'Queue export blocked (Confirm=PREVIEW). Use -Confirm APPLY to write SOCIAL/QUEUE/.'
  exit 0
}

if (-not $ExportQueue) {
  Write-Host 'APPLY requested but -ExportQueue is disabled; no queue written.'
  exit 0
}

# APPLY: export queue only if all drafts pass checks
$blocked = @($previewItems | Where-Object { (-not $_.banned_pass) -or (-not $_.hashtag_ok) -or (-not $_.emoji_ok) })
if ($blocked.Count -gt 0) {
  Write-Host ''
  Write-Host '=== APPLY REFUSED (queue export blocked due to FAIL drafts) ==='
  foreach ($b in $blocked) {
    Write-Host ("Post #{0} is FAIL; fix and re-run APPLY." -f $b.index)
  }
  exit 3
}

$queueName = "{0}_queue.md" -f $today
$queuePath = Join-Path $queueDir $queueName

foreach ($p in $previewItems) {
  $queueBlock = @(
    ("# {0} {1} {2}" -f $today, $Account, $Platform),
    $p.text,
    '---',
    ("source_sha256: {0}" -f $sourceHash),
    ("policy_sha256: {0}" -f $policyHash),
    ''
  ) -join "`n"

  Add-Content -LiteralPath $queuePath -Value ($queueBlock + "`n") -Encoding UTF8
}

Write-Host ''
Write-Host '=== APPLY COMPLETE ==='
Write-Host ("Drafts written: {0}" -f $writtenDrafts.Count)
Write-Host ("Queue written:  {0}" -f $queuePath)
