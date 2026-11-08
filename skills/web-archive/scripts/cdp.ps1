<#
.SYNOPSIS
  CDP 通用求值器：连到指定标签页，执行一段 JS，打印结果。
  也支持派发真实鼠标事件（合成 dispatchEvent 失效时的唯一出路）。

.DESCRIPTION
  这是所有拓存脚本的公共底座。实现要点（PowerShell 5.1 兼容）：
    - 用 .NET 的 ClientWebSocket 手搓 CDP 客户端（无需 node / puppeteer / 任何依赖）
    - Runtime.evaluate 必须带 returnByValue + awaitPromise，否则拿不到异步结果
    - ConvertTo-Json 的 -Depth 必须给足（6~12），否则嵌套结构被压成字符串
    - 接收缓冲区给到 16MB+：长文档单帧 payload 可能很大
    - 消息流里混着事件帧，必须按 id 匹配响应，不能读一帧就当结果

.EXAMPLE
  # 执行探针，打印 JSON
  powershell -File cdp.ps1 -JsFile probe-dom.js

  # 按 URL 关键字挑标签页
  powershell -File cdp.ps1 -JsFile probe-dom.js -UrlMatch "alidocs"

  # 直接执行内联表达式
  powershell -File cdp.ps1 -Expression "document.title"

  # 双击（真实鼠标事件）——用于打开目录树行等
  powershell -File cdp.ps1 -DoubleClickSelector "[data-rbd-draggable-id='abc']"
#>
param(
  [string]$JsFile,
  [string]$Expression,
  [string]$UrlMatch = "",          # 标签页 URL 关键字过滤
  [int]$Port = 9333,
  [int]$TimeoutMs = 60000,
  [string]$DoubleClickSelector,     # 若给出，则对该元素派发真实双击
  [int]$NewTabWaitSec = 0
)

$ErrorActionPreference = 'Stop'

# ================= 公共函数（可被其它脚本 dot-source） =================

function Get-CdpTargets {
  param([int]$P)
  $data = Invoke-RestMethod -Uri "http://127.0.0.1:$P/json" -Method Get -TimeoutSec 10
  foreach ($item in @($data)) { $item }
}

function Select-CdpTab {
  param([int]$P, [string]$Match)
  $pages = @(Get-CdpTargets $P | Where-Object { $_.type -eq 'page' })
  if ($Match) {
    $hit = $pages | Where-Object { $_.url -like "*$Match*" } | Select-Object -First 1
    if ($hit) { return $hit }
  }
  return ($pages | Select-Object -First 1)
}

function Receive-Cdp {
  param([System.Net.WebSockets.ClientWebSocket]$Ws, [int]$BufferMB = 24)
  $buffer = New-Object byte[] ($BufferMB * 1MB)
  $sb = New-Object System.Text.StringBuilder
  while ($true) {
    $seg = [ArraySegment[byte]]::new($buffer)
    $res = $Ws.ReceiveAsync($seg, [System.Threading.CancellationToken]::None).GetAwaiter().GetResult()
    if ($res.Count -eq 0) { return $null }
    [void]$sb.Append([System.Text.Encoding]::UTF8.GetString($buffer, 0, $res.Count))
    if ($res.EndOfMessage) { break }
  }
  return $sb.ToString()
}

function Invoke-CdpEval {
  <# 发送 Runtime.evaluate 并等待匹配 id 的响应。返回 response 对象。 #>
  param(
    [System.Net.WebSockets.ClientWebSocket]$Ws,
    [ref]$CdpId,
    [string]$Expr,
    [int]$TimeoutMs = 60000,
    [switch]$AwaitPromise
  )
  $id = $CdpId.Value
  $CdpId.Value = $id + 1
  $params = @{
    expression    = $Expr
    returnByValue = $true
    awaitPromise  = [bool]$AwaitPromise
    timeout       = $TimeoutMs
  }
  $payload = @{ id = $id; method = 'Runtime.evaluate'; params = $params } | ConvertTo-Json -Depth 8 -Compress
  $bytes = [System.Text.Encoding]::UTF8.GetBytes($payload)
  $Ws.SendAsync([ArraySegment[byte]]::new($bytes), 'Text', $true, [System.Threading.CancellationToken]::None).GetAwaiter().GetResult() | Out-Null

  $deadline = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() + $TimeoutMs + 10000
  while ([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() -lt $deadline) {
    $resp = Receive-Cdp $Ws
    if (-not $resp) { return $null }
    $obj = $null
    try { $obj = $resp | ConvertFrom-Json } catch { continue }
    # 事件帧没有 id，跳过
    if ($null -ne $obj.id -and $obj.id -eq $id) { return $obj }
  }
  return $null
}

function Get-CdpEvalValue {
  param(
    [System.Net.WebSockets.ClientWebSocket]$Ws,
    [ref]$CdpId,
    [string]$Expr,
    [int]$TimeoutMs = 60000,
    [switch]$AwaitPromise
  )
  $r = Invoke-CdpEval -Ws $Ws -CdpId $CdpId -Expr $Expr -TimeoutMs $TimeoutMs -AwaitPromise:$AwaitPromise
  if ($r -and $r.result -and $r.result.result) { return $r.result.result.value }
  return $null
}

function Connect-CdpWs {
  param([string]$WsUrl)
  $ws = [System.Net.WebSockets.ClientWebSocket]::new()
  # CDP is a loopback connection. Do not route it through the user's system HTTP proxy.
  $ws.Options.Proxy = $null
  $ws.ConnectAsync([Uri]$WsUrl, [System.Threading.CancellationToken]::None).GetAwaiter().GetResult() | Out-Null
  return $ws
}

function Invoke-CdpMouseClick {
  <# 派发真实鼠标事件（mousedown/mouseup + clickCount）。
     很多框架不响应 JS 合成的 dispatchEvent，必须走这条路。 #>
  param(
    [System.Net.WebSockets.ClientWebSocket]$Ws,
    [ref]$CdpId,
    [int]$X, [int]$Y, [int]$ClickCount = 1
  )
  foreach ($phase in @('mousePressed', 'mouseReleased')) {
    $p = @{ type = $phase; x = $X; y = $Y; button = 'left'; clickCount = $ClickCount; pointerType = 'mouse' }
    if ($phase -eq 'mousePressed') { $p.buttons = 1 }
    $id = $CdpId.Value; $CdpId.Value = $id + 1
    $payload = @{ id = $id; method = 'Input.dispatchMouseEvent'; params = $p } | ConvertTo-Json -Depth 6 -Compress
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($payload)
    $Ws.SendAsync([ArraySegment[byte]]::new($bytes), 'Text', $true, [System.Threading.CancellationToken]::None).GetAwaiter().GetResult() | Out-Null
    Start-Sleep -Milliseconds 120
  }
}

# ================= 主流程（直接执行时生效） =================
if ($MyInvocation.InvocationName -ne '.') {
  if ([string]::IsNullOrWhiteSpace($JsFile) -and [string]::IsNullOrWhiteSpace($Expression) -and [string]::IsNullOrWhiteSpace($DoubleClickSelector)) {
    Write-Host "用法: cdp.ps1 -JsFile <file.js> | -Expression <js> | -DoubleClickSelector <css> [-UrlMatch <s>] [-Port 9333]"
    exit 1
  }

  $tab = Select-CdpTab -P $Port -Match $UrlMatch
  if (-not $tab) { Write-Host "NO-TAB (port=$Port, match='$UrlMatch')"; exit 1 }
  Write-Host "[cdp] tab: $($tab.url)"

  $ws = Connect-CdpWs $tab.webSocketDebuggerUrl
  $cdpId = [ref]1

  if ($DoubleClickSelector) {
    $rectJson = Get-CdpEvalValue -Ws $ws -CdpId $cdpId -Expr @"
(function(){
  const el = document.querySelector(`$DoubleClickSelector`);
  if (!el) return null;
  const r = el.getBoundingClientRect();
  return JSON.stringify({x: Math.round(r.left + r.width/2), y: Math.round(r.top + r.height/2)});
})()
"@ -TimeoutMs 20000
    if (-not $rectJson) { Write-Host "SELECTOR-NOT-FOUND"; $ws.Dispose(); exit 1 }
    $rect = $rectJson | ConvertFrom-Json
    Write-Host "[cdp] double-click at $($rect.x),$($rect.y)"
    Invoke-CdpMouseClick -Ws $ws -CdpId $cdpId -X $rect.x -Y $rect.y -ClickCount 1
    Start-Sleep -Milliseconds 400
    Invoke-CdpMouseClick -Ws $ws -CdpId $cdpId -X $rect.x -Y $rect.y -ClickCount 2
    Start-Sleep -Seconds 3
    Write-Host "[cdp] url now: $(Get-CdpEvalValue -Ws $ws -CdpId $cdpId -Expr 'location.href' -TimeoutMs 15000)"
    $ws.Dispose()
    exit 0
  }

  $expr = $Expression
  if (-not $expr -and $JsFile) {
    if (-not (Test-Path $JsFile)) { Write-Host "JS-FILE-NOT-FOUND: $JsFile"; exit 1 }
    $expr = [System.IO.File]::ReadAllText((Resolve-Path $JsFile).Path)
  }

  $val = Get-CdpEvalValue -Ws $ws -CdpId $cdpId -Expr $expr -TimeoutMs $TimeoutMs -AwaitPromise
  if ($null -eq $val) { Write-Host "EVAL-NULL-OR-ERROR" } else { Write-Host $val }
  $ws.Dispose()
}
