<#
Invoke-VaFormsFetch.ps1
Downloads VA forms into category folders using:
- Known PDF URLs (mostly insurance)
- Optional VA Forms API lookup to resolve PDF URLs for other forms

Requirements:
- PowerShell 5.1+ (Windows) or PowerShell 7+
- Optional: set $env:VA_API_KEY (VA Lighthouse API key) for VA Forms API lookups

Notes:
- Produces *.sha256.txt and *.meta.txt alongside each PDF for integrity + traceability.
- If a PDF URL can't be resolved, writes a *.meta.txt pointer with lookup_url.
#>

[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)]
  [string]$ManifestCsvPath,

  [Parameter(Mandatory=$true)]
  [string]$OutDir
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function New-Folder([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path)) {
    New-Item -ItemType Directory -Path $Path | Out-Null
  }
}

function Get-Sha256Hex([string]$FilePath) {
  return (Get-FileHash -Algorithm SHA256 -LiteralPath $FilePath).Hash.ToLowerInvariant()
}

function Save-Text([string]$Path, [string]$Text) {
  $Text | Out-File -LiteralPath $Path -Encoding utf8 -Force
}

function Normalize-FormId([string]$formId) {
  # Standardize common separators for filenames
  return ($formId.Trim() -replace '[^a-zA-Z0-9\-]+','-')
}

function Sanitize-FileNameComponent([string]$Value) {
  if ($null -eq $Value) { return '' }

  $invalid = [IO.Path]::GetInvalidFileNameChars()
  $sb = New-Object System.Text.StringBuilder
  foreach ($ch in $Value.ToCharArray()) {
    if ($invalid -contains $ch) {
      [void]$sb.Append('_')
    } else {
      [void]$sb.Append($ch)
    }
  }

  return ($sb.ToString().Trim())
}

function Invoke-Download([string]$Url, [string]$OutFile) {
  # Use Invoke-WebRequest for broad compatibility
  Write-Host "  DOWN $Url"
  Invoke-WebRequest -Uri $Url -OutFile $OutFile -UseBasicParsing
}

function Resolve-PdfUrlViaVaFormsApi([string]$FormId) {
  $apiKey = $env:VA_API_KEY
  if ([string]::IsNullOrWhiteSpace($apiKey)) { return $null }

  # VA Forms API: GET /services/va_forms/v0/forms?query=
  $base = "https://api.va.gov/services/va_forms/v0/forms"
  $q = [System.Web.HttpUtility]::UrlEncode($FormId)
  $url = "$base?query=$q"

  try {
    $resp = Invoke-RestMethod -Uri $url -Headers @{ apikey = $apiKey }
  } catch {
    # Some users may only have sandbox access; try sandbox if prod fails
    $sandbox = "https://sandbox-api.va.gov/services/va_forms/v0/forms?query=$q"
    try {
      $resp = Invoke-RestMethod -Uri $sandbox -Headers @{ apikey = $apiKey }
    } catch {
      return $null
    }
  }

  $items = $resp.data
  if ($null -eq $items) { return $null }

  $best = $items | Select-Object -First 1
  if ($null -eq $best) { return $null }

  $attrs = $best.attributes
  if ($null -eq $attrs) { return $null }

  if ($attrs.pdf_url) { return [string]$attrs.pdf_url }
  if ($attrs.url) { return [string]$attrs.url }

  foreach ($p in $attrs.PSObject.Properties) {
    $v = [string]$p.Value
    if ($v -match '\\.pdf($|\\?)') { return $v }
  }

  return $null
}

# ---- Main ----
New-Folder $OutDir

$rows = Import-Csv -LiteralPath $ManifestCsvPath
if ($rows.Count -eq 0) { throw "Manifest CSV is empty: $ManifestCsvPath" }

$logPath = Join-Path $OutDir ("download-log-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".txt")

"VA Forms Fetch Run: $(Get-Date -Format o)" | Out-File -LiteralPath $logPath -Encoding utf8 -Force
"Manifest: $ManifestCsvPath" | Out-File -LiteralPath $logPath -Encoding utf8 -Append
"Output:   $OutDir" | Out-File -LiteralPath $logPath -Encoding utf8 -Append
"VA_API_KEY present: " + (-not [string]::IsNullOrWhiteSpace($env:VA_API_KEY)) | Out-File -LiteralPath $logPath -Encoding utf8 -Append
"" | Out-File -LiteralPath $logPath -Encoding utf8 -Append

foreach ($r in $rows) {
  $category = $r.category.Trim()
  $formId = $r.form_id.Trim()
  $titleHint = $r.title_hint
  $pdfKnown = $r.pdf_url_known

  $safeCategory = Sanitize-FileNameComponent $category
  $catDir = Join-Path $OutDir $safeCategory
  New-Folder $catDir

  $safeId = Normalize-FormId $formId
  $pdfPath = Join-Path $catDir ("$safeId.pdf")
  $shaPath = Join-Path $catDir ("$safeId.sha256.txt")
  $metaPath = Join-Path $catDir ("$safeId.meta.txt")

  if (Test-Path -LiteralPath $pdfPath) {
    Write-Host "[SKIP] $category :: $formId (already exists)"
    continue
  }

  Write-Host "[GET ] $category :: $formId"

  $resolvedUrl = $null

  if (-not [string]::IsNullOrWhiteSpace($pdfKnown)) {
    $resolvedUrl = $pdfKnown.Trim()
  } else {
    $resolvedUrl = Resolve-PdfUrlViaVaFormsApi $formId
  }

  if ([string]::IsNullOrWhiteSpace($resolvedUrl)) {
    $pointer = @()
    $pointer += "FORM: $formId"
    $pointer += "CATEGORY: $category"
    if ($titleHint) { $pointer += "TITLE_HINT: $titleHint" }
    if ($r.lookup_url) { $pointer += "LOOKUP_URL: $($r.lookup_url)" }
    $pointer += "STATUS: NOT_DOWNLOADED (no direct pdf url; set VA_API_KEY to enable API resolution)"
    Save-Text $metaPath ($pointer -join "`r`n")

    "MISS  $category :: $formId  (no pdf url resolved)" | Out-File -LiteralPath $logPath -Encoding utf8 -Append
    continue
  }

  try {
    Invoke-Download -Url $resolvedUrl -OutFile $pdfPath
    $sha = Get-Sha256Hex $pdfPath
    Save-Text $shaPath $sha

    $meta = @()
    $meta += "FORM: $formId"
    $meta += "CATEGORY: $category"
    if ($titleHint) { $meta += "TITLE_HINT: $titleHint" }
    $meta += "SOURCE_URL: $resolvedUrl"
    $meta += "SHA256: $sha"
    Save-Text $metaPath ($meta -join "`r`n")

    "OK    $category :: $formId  $sha" | Out-File -LiteralPath $logPath -Encoding utf8 -Append
  } catch {
    "FAIL  $category :: $formId  $($_.Exception.Message)" | Out-File -LiteralPath $logPath -Encoding utf8 -Append
    if (Test-Path -LiteralPath $pdfPath) { Remove-Item -LiteralPath $pdfPath -Force -ErrorAction SilentlyContinue }
    continue
  }
}

Write-Host ""
Write-Host "Done. Log: $logPath"
Write-Host "Note: Any *.meta.txt marked NOT_DOWNLOADED needs VA_API_KEY or manual download via lookup_url."
