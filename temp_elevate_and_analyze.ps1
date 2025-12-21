# Temporary helper: install PSScriptAnalyzer and run analysis
try {
    Install-Module -Name PSScriptAnalyzer -Force -AllowClobber -Scope AllUsers -ErrorAction Stop
} catch {
    Write-Output "Install-Module failed: $_"
}
try {
    Import-Module PSScriptAnalyzer -ErrorAction SilentlyContinue
} catch {}
$out = 'C:\baseline-algorithms-and-programs\artifacts\psscriptanalyzer_output.txt'
try {
    $res = Invoke-ScriptAnalyzer -Path 'C:\baseline-algorithms-and-programs\scripts' -Recurse -Severity Warning,Error -ErrorAction Stop | Out-String
    $res | Out-File -FilePath $out -Encoding utf8
    Write-Output "Analyzer run completed, output written to $out"
} catch {
    "Analyzer run failed: $_" | Out-File -FilePath $out -Encoding utf8
    Write-Output "Analyzer run failed; details in $out"
}
Write-Output "Script finished."