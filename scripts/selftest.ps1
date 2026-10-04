# Runs tests/selftest.html in headless Chrome against a throwaway local web server and prints the results.
# Usage (from the repo folder): powershell -ExecutionPolicy Bypass -File scripts/selftest.ps1
# Exits 1 if any check fails or the page never finishes. CI runs the same page from .github/workflows/selftest.yml.
param([int]$Port = 8123, [string]$Page = 'tests/selftest.html')
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

$chrome = @("$env:ProgramFiles\Google\Chrome\Application\chrome.exe", "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
  "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe", "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe") |
  Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $chrome) { Write-Error 'Chrome or Edge not found.' }

# a minimal static file server, in a background job so Chrome can fetch the page, the fixture and index.html
$server = Start-Job -ArgumentList $root, $Port -ScriptBlock {
  param($root, $port)
  $types = @{ '.html' = 'text/html; charset=utf-8'; '.json' = 'application/json'; '.js' = 'text/javascript'; '.css' = 'text/css'; '.svg' = 'image/svg+xml'; '.png' = 'image/png' }
  $l = New-Object System.Net.HttpListener; $l.Prefixes.Add("http://localhost:$port/"); $l.Start()
  while ($l.IsListening) {
    $c = $l.GetContext()
    $path = Join-Path $root ([Uri]::UnescapeDataString($c.Request.Url.AbsolutePath.TrimStart('/')))
    if (Test-Path $path -PathType Leaf) {
      $bytes = [IO.File]::ReadAllBytes($path); $ext = [IO.Path]::GetExtension($path)
      $c.Response.ContentType = if ($types[$ext]) { $types[$ext] } else { 'application/octet-stream' }
      $c.Response.OutputStream.Write($bytes, 0, $bytes.Length)
    } else { $c.Response.StatusCode = 404 }
    $c.Response.Close()
  }
}
try {
  Start-Sleep -Milliseconds 800
  $prof = Join-Path ([IO.Path]::GetTempPath()) ('bp-selftest-' + [Guid]::NewGuid())
  $dom = & $chrome --headless=new --disable-gpu --no-first-run --user-data-dir="$prof" --virtual-time-budget=120000 `
    --dump-dom "http://localhost:$Port/$Page" 2>$null | Out-String
  Remove-Item -Recurse -Force $prof -ErrorAction SilentlyContinue
  $m = [regex]::Match($dom, '<pre id="selftest-out">(.*?)</pre>', 'Singleline')
  if (-not $m.Success) { Write-Host 'FAIL no results in the page'; exit 1 }
  $text = [Net.WebUtility]::HtmlDecode($m.Groups[1].Value)
  Write-Host $text
  if ($text -match '(?m)^FAIL' -or $text -notmatch '(?m)^DONE') { exit 1 }
} finally {
  Stop-Job $server -ErrorAction SilentlyContinue; Remove-Job $server -Force -ErrorAction SilentlyContinue
}
