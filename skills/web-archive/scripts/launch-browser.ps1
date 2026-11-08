<#
.SYNOPSIS
  以「远程调试 + 持久化用户目录」模式启动 Chromium 系浏览器，用于网页拓存。

.DESCRIPTION
  关键点：
    1. --remote-debugging-port  暴露 CDP 端口，供后续脚本接管页面
    2. --user-data-dir          独立持久化 profile —— 登录态长期复用（一次登录，之后免登录）
    3. 不占用用户日常浏览器 profile，避免互相干扰

  幂等：若端口已在监听，直接返回，不重复启动。

.EXAMPLE
  powershell -File launch-browser.ps1
  powershell -File launch-browser.ps1 -Port 9333 -ProfileDir "D:\tmp\wb-profile"
#>
param(
  [int]$Port = 9333,
  [string]$ProfileDir = "",
  [string]$StartUrl = "about:blank",
  [switch]$Force   # 端口已被别的进程占用时，仍尝试启动（一般不需要）
)

$ErrorActionPreference = 'Stop'

# ---------- 端口探测（幂等） ----------
function Test-CdpPort {
  param([int]$P)
  try {
    $r = Invoke-RestMethod -Uri "http://127.0.0.1:$P/json/version" -TimeoutSec 3
    return $null -ne $r.webSocketDebuggerUrl
  } catch { return $false }
}

if (Test-CdpPort $Port) {
  Write-Host "[launch] CDP port $Port already listening — reusing existing browser."
  exit 0
}

# ---------- profile 目录 ----------
if ([string]::IsNullOrWhiteSpace($ProfileDir)) {
  $ProfileDir = Join-Path $env:LOCALAPPDATA "web-archive-profile"
}
if (-not (Test-Path $ProfileDir)) { New-Item -ItemType Directory -Path $ProfileDir -Force | Out-Null }
$ProfileDir = (Resolve-Path $ProfileDir).Path
Write-Host "[launch] profile: $ProfileDir"

# ---------- 定位浏览器 ----------
function Find-Browser {
  $cands = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe",
    "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
    "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
    "$env:ProgramFiles\Chromium\Application\chrome.exe"
  )
  foreach ($c in $cands) { if ($c -and (Test-Path $c)) { return $c } }
  # 兜底：注册表里找 Chrome
  try {
    $reg = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe' -ErrorAction SilentlyContinue
    if ($reg -and $reg.'(default)' -and (Test-Path $reg.'(default)')) { return $reg.'(default)' }
  } catch {}
  return $null
}

$exe = Find-Browser
if (-not $exe) {
  Write-Host "[launch] ERROR: 未找到 Chrome / Edge / Chromium。请安装其中之一，或用 -Exe 指定路径。"
  exit 1
}
Write-Host "[launch] browser: $exe"

# ---------- 启动 ----------
$args = @(
  "--remote-debugging-port=$Port",
  "--user-data-dir=$ProfileDir",
  "--no-first-run",
  "--no-default-browser-check",
  "--disable-features=Translate",
  $StartUrl
)
Start-Process -FilePath $exe -ArgumentList $args | Out-Null

# ---------- 等待端口就绪 ----------
$deadline = (Get-Date).AddSeconds(30)
while ((Get-Date) -lt $deadline) {
  if (Test-CdpPort $Port) {
    $v = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/json/version" -TimeoutSec 3
    Write-Host "[launch] READY  port=$Port  browser=$($v.Browser)"
    exit 0
  }
  Start-Sleep -Milliseconds 700
}

Write-Host "[launch] ERROR: 端口 $Port 在 30s 内未就绪。"
exit 1
