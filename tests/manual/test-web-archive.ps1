param(
  [string]$BrowserPath = "",
  [int]$Port = 9555,
  [switch]$KeepTemp
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)   # tests/manual/ → 仓库根
$scripts = Join-Path $root 'skills\web-archive\scripts'
$fixtures = Join-Path $PSScriptRoot 'fixtures'
$tempRoot = Join-Path $env:TEMP ("web-archive-test-{0}" -f [guid]::NewGuid().ToString('N'))
$profile = Join-Path $tempRoot 'profile'
$renderRoot = Join-Path $tempRoot 'render'
New-Item -ItemType Directory -Force -Path $profile, $renderRoot | Out-Null

function Assert-Contains([string]$Name, [string]$Text, [string]$Needle) {
  if (-not $Text.Contains($Needle)) {
    throw "[$Name] missing expected text: $Needle"
  }
}

function Close-TestTab([string]$UrlPart) {
  try {
    $targets = Invoke-RestMethod "http://127.0.0.1:$Port/json" -TimeoutSec 3
    foreach ($target in @($targets | Where-Object { $_.url -like "*$UrlPart*" })) {
      Invoke-RestMethod "http://127.0.0.1:$Port/json/close/$($target.id)" -Method Get -TimeoutSec 3 | Out-Null
    }
  } catch {}
}

if ([string]::IsNullOrWhiteSpace($BrowserPath)) {
  $candidates = @(
    'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
    'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
    'C:\Program Files\Google\Chrome\Application\chrome.exe',
    'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe'
  )
  $BrowserPath = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $BrowserPath) { throw 'Chrome or Edge not found.' }

foreach ($file in Get-ChildItem (Join-Path $scripts '*.ps1')) {
  $tokens = $null; $errors = $null
  [void][System.Management.Automation.Language.Parser]::ParseFile($file.FullName, [ref]$tokens, [ref]$errors)
  if ($errors.Count) { throw "PowerShell syntax failed: $($file.Name): $($errors.Message -join '; ')" }
}
node --check (Join-Path $scripts 'probe-dom.js')
if ($LASTEXITCODE -ne 0) { throw 'probe-dom.js syntax failed.' }

$browser = Start-Process -FilePath $BrowserPath -WindowStyle Hidden -PassThru -ArgumentList @(
  '--headless=new',
  '--disable-gpu',
  '--no-sandbox',
  '--disable-dev-shm-usage',
  "--remote-debugging-port=$Port",
  '--remote-allow-origins=*',
  '--no-first-run',
  '--no-default-browser-check',
  "--user-data-dir=$profile",
  'about:blank'
)

try {
  $deadline = (Get-Date).AddSeconds(30)
  do {
    Start-Sleep -Milliseconds 500
    try { $version = Invoke-RestMethod "http://127.0.0.1:$Port/json/version" -TimeoutSec 2 } catch { $version = $null }
  } until ($version -or (Get-Date) -ge $deadline)
  if (-not $version) { throw 'CDP did not become ready.' }

  $cases = @(
    @{
      Name = 'dingtalk'
      File = 'web-archive-smoke.html'
      Adapter = 'dingtalk'
      Needles = @(
        '# Web Archive Smoke Test',
        '> 引用内容保持原样。',
        '```brainfuck',
        '```mermaid',
        'graph TD;A-->B;',
        'Mermaid 源码未在 DOM 中暴露',
        '指标名称',
        '合并'
      )
    },
    @{
      Name = 'feishu'
      File = 'web-archive-feishu-smoke.html'
      Adapter = 'feishu'
      Needles = @(
        '# 飞书块模型冒烟',
        '飞书 **块属性** 已进入统一格式。',
        '```elixir',
        'flowchart LR;A-->B'
      )
    },
    @{
      Name = 'generic'
      File = 'web-archive-generic-smoke.html'
      Adapter = 'generic'
      Needles = @(
        '# 普通防复制页面',
        '- 第一项',
        '- **第二项**',
        '1. 第一步',
        '2. 第二步',
        '3. 第三步',
        '4. 第四步',
        '> 第一段引用。',
        '> 第二段引用。',
        '```c#',
        '```mermaid',
        'sequenceDiagram;A->>B: ok',
        '跨行'
      )
    }
  )

  foreach ($case in $cases) {
    $outDir = Join-Path $tempRoot ("work-{0}" -f $case.Name)
    $url = 'file:///' + ((Join-Path $fixtures $case.File) -replace '\\', '/')
    $log = & (Join-Path $scripts 'harvest.ps1') -Url $url -Prefix $case.Name -OutDir $outDir -Port $Port -Adapter $case.Adapter -SingleView -KeepTab 2>&1
    $windowFile = Join-Path $outDir ("{0}_w1.json" -f $case.Name)
    if (-not (Test-Path $windowFile)) { throw "[$($case.Name)] harvest produced no window file: $($log -join '; ')" }
    & (Join-Path $scripts 'merge-blocks.ps1') -Dir $outDir -Prefix $case.Name | Out-Null
    $merged = Join-Path $outDir ("merged_{0}.json" -f $case.Name)
    $rendered = Join-Path $renderRoot ("{0}.md" -f $case.Name)
    & (Join-Path $scripts 'render-md.ps1') -MergedPath $merged -Title $case.Name -Source $url -OutPath $rendered | Out-Null
    $markdown = Get-Content -Raw -Encoding utf8 $rendered
    foreach ($needle in $case.Needles) { Assert-Contains $case.Name $markdown $needle }
    if ($case.Name -eq 'dingtalk' -and ([regex]::Matches($markdown, '合并').Count -lt 2)) {
      throw '[dingtalk] rowSpan cell content was not expanded into both rows.'
    }
    if ($case.Name -eq 'dingtalk' -and ([regex]::Matches($markdown, 'Mermaid 源码未在 DOM 中暴露').Count -lt 2)) {
      throw '[dingtalk] both image-backed and inline-SVG Mermaid fallbacks must be preserved.'
    }
    if ($case.Name -eq 'generic' -and ([regex]::Matches($markdown, '跨行').Count -lt 2)) {
      throw '[generic] rowSpan cell content was not expanded into both rows.'
    }
    if ($case.Name -eq 'generic' -and ([regex]::Matches($markdown, '列 B').Count -lt 2)) {
      throw '[generic] colSpan header content was not expanded into both columns.'
    }
    Write-Host "[PASS] $($case.Name)"
    Close-TestTab $case.File
  }

  $loginUrl = 'file:///' + ((Join-Path $fixtures 'web-archive-login-wall.html') -replace '\\', '/')
  $loginOut = Join-Path $tempRoot 'work-login'
  $loginLog = & (Join-Path $scripts 'harvest.ps1') -Url $loginUrl -Prefix login -OutDir $loginOut -Port $Port -Adapter generic -SingleView -KeepTab *>&1
  $loginText = $loginLog -join "`n"
  if ($loginText -notmatch 'login-required') { throw "[login] expected login-required, got: $loginText" }
  Write-Host '[PASS] login-wall'
  Close-TestTab 'web-archive-login-wall.html'

  $stallUrl = 'file:///' + ((Join-Path $fixtures 'web-archive-stall-smoke.html') -replace '\\', '/')
  $stallOut = Join-Path $tempRoot 'work-stall'
  $stallLog = & (Join-Path $scripts 'harvest.ps1') -Url $stallUrl -Prefix stall -OutDir $stallOut -Port $Port -Adapter generic -MaxStalledWindows 1 -MaxWindows 10 -KeepTab *>&1
  $stallText = $stallLog -join "`n"
  if ($stallText -notmatch '连续 1 窗无新内容') { throw "[stall] expected no-progress guard, got: $stallText" }
  Write-Host '[PASS] stall-guard'
  Close-TestTab 'web-archive-stall-smoke.html'

  Write-Host 'ALL WEB-ARCHIVE TESTS PASSED'
}
finally {
  if ($browser -and -not $browser.HasExited) { Stop-Process -Id $browser.Id -Force -ErrorAction SilentlyContinue }
  if (-not $KeepTemp) {
    $resolvedTemp = [IO.Path]::GetFullPath($tempRoot)
    $resolvedBase = [IO.Path]::GetFullPath($env:TEMP).TrimEnd('\') + '\'
    if ($resolvedTemp.StartsWith($resolvedBase, [StringComparison]::OrdinalIgnoreCase) -and
        (Split-Path -Leaf $resolvedTemp) -like 'web-archive-test-*') {
      Remove-Item -LiteralPath $resolvedTemp -Recurse -Force -ErrorAction SilentlyContinue
    } else {
      Write-Warning "Refusing to remove unexpected temp path: $resolvedTemp"
    }
  }
}
