# CDP 操作配方

Chrome DevTools Protocol 是这套拓存方案的唯一底座。**不需要 puppeteer / playwright / selenium / 任何浏览器插件**——用裸 CDP + HTTP + WebSocket 就能全部搞定。

## 1. 启动浏览器（调试模式 + 持久化登录态）

```powershell
powershell -File scripts/launch-browser.ps1 -Port 9333
```

等价的原生命令：

```
chrome.exe --remote-debugging-port=9333 ^
           --user-data-dir="%LOCALAPPDATA%\web-archive-profile" ^
           --no-first-run --no-default-browser-check about:blank
```

**`--user-data-dir` 是整个方案的关键**：登录态（Cookie / localStorage）持久化在这个独立 profile 里。用户第一次手动登录一次，之后所有采集会话都免登录。不要用用户日常 profile，避免互相干扰与误操作。

## 2. HTTP 端点（目标发现）

| 方法 | 端点 | 作用 |
|---|---|---|
| GET | `/json/version` | 健康检查，返回 `Browser` 与 `webSocketDebuggerUrl` |
| GET | `/json` | 列出全部 target（标签页 / service worker / iframe） |
| PUT | `/json/new?<urlencoded-url>` | **新建标签页**（注意是 PUT，不是 POST/GET） |
| GET | `/json/close/<targetId>` | 关闭标签页 |

```powershell
# 只看 page 类型
Invoke-RestMethod -Uri "http://127.0.0.1:9333/json" -Method Get |
  Where-Object { $_.type -eq 'page' } | Select-Object id, url, webSocketDebuggerUrl
```

> `/json` 返回里 `type` 可能是 `page` / `iframe` / `service_worker` / `other`。
> **必须过滤 `type -eq 'page'`**，否则可能连到一个 iframe target 上，`document` 就不是你以为的那个文档。

## 3. WebSocket CDP 会话

拿到 `webSocketDebuggerUrl` 后连上去，发 JSON 帧：

```json
{ "id": 1, "method": "Runtime.evaluate",
  "params": { "expression": "document.title", "returnByValue": true, "awaitPromise": false } }
```

响应是 `{ "id": 1, "result": { "result": { "type": "string", "value": "..." } } }`。

### 常用方法

| method | 用途 | 关键 params |
|---|---|---|
| `Runtime.evaluate` | 执行 JS、取返回值 | `expression`、`returnByValue:true`、`awaitPromise`、`timeout` |
| `Input.dispatchMouseEvent` | 派发**真实**鼠标事件 | `type`(mousePressed/mouseReleased)、`x`、`y`、`button`、`clickCount`、`buttons` |
| `Page.enable` | 开启页面事件 | — |
| `Page.navigate` | 导航 | `url` |
| `Runtime.enable` | 开启运行时事件 | — |

### 消息流处理（最容易踩的坑）

WebSocket 上**事件帧与响应帧混在一起**，事件帧没有 `id`。所以：

1. 每条请求分配自增 `id`
2. 循环 `Receive`，逐帧 `ConvertFrom-Json`
3. **只在 `obj.id -eq $sentId` 时才认为拿到结果**，否则继续读
4. 用 deadline 兜底，超时返回 `$null`（不要死等）

长文档单帧 payload 可能很大 → **接收缓冲区给 16MB 以上**，且要循环 `ReceiveAsync` 直到 `EndOfMessage`。

## 4. PowerShell 5.1 硬约束（Windows 自带版本）

| 限制 | 正确写法 |
|---|---|
| 没有 `&&` / `\|\|` | 用 `;` 或 `if ($?) { }` |
| 没有三元 `?:` | 用 `if (...) { } else { }` 赋值 |
| 没有 `??` / `?.` | 显式判 `$null` |
| 时间戳 | `[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()`（**不要自己算**） |
| `ConvertTo-Json` 默认深度 2 | **必须显式 `-Depth`**：求值参数用 6~8，写复杂对象用 12~14 |
| 中文输出乱码 | 文件读写统一 `[System.Text.Encoding]::UTF8`；新建文件用 `UTF8Encoding($true)` 带 BOM 更稳 |
| `$Matches` 在管道/函数内易丢 | 需要时立刻 `$m = $Matches`，或改用 `[regex]::Match(...)` |
| `.ps1` 里中文 | 存为 UTF-8 **with BOM**，避免 PS 5.1 按 ANSI 解码导致中文乱码 |

### ⚠️ 最容易误判的坑：`.ps1` 必须是 UTF-8 **with BOM**

PowerShell 5.1 读取 `.ps1` 时**默认按系统 ANSI 代码页解码**（中文 Windows 上是 GBK），
**不认 UTF-8 without BOM**。后果不是简单的"中文显示乱码"，而是：

> 含中文的字符串/注释被错误解码后，**引号、括号配对被打乱**，
> 解析器报告出一堆**看起来像真实语法错误**的消息 ——
> 比如"标记 `&&` 不是有效语句分隔符"、"字符串缺少终止符"、"数组索引表达式丢失或无效"，
> 甚至会指向你根本没写过 `&&` 的行号。

**踩坑特征**：报错内容与源码实际写法对不上，且报错集中在含中文的行附近。
**处置**：直接给文件加 BOM，然后重跑语法检查——绝大多数"语法错误"会瞬间消失。

```powershell
# 批量补 BOM
Get-ChildItem *.ps1 | ForEach-Object {
  $t = [System.IO.File]::ReadAllText($_.FullName, [System.Text.Encoding]::UTF8)
  [System.IO.File]::WriteAllText($_.FullName, $t, (New-Object System.Text.UTF8Encoding($true)))
}
```

**写脚本后的固定动作：先做语法检查，别急着执行。**

```powershell
$errs = $null
[void][System.Management.Automation.Language.Parser]::ParseFile("script.ps1", [ref]$null, [ref]$errs)
if ($errs) { $errs | ForEach-Object { "L{0}: {1}" -f $_.Extent.StartLineNumber, $_.Message } }
```

> **不要**把带非 ASCII 路径的脚本写成 `.bat` / `.ps1` 再执行——编码会把路径搞坏。直接用工具调用带参数执行。

## 5. 真实鼠标事件（`Input.dispatchMouseEvent`）

**这是本方案里最重要的一个"绕不过去"的技巧。**

很多前端框架（React / 自研组件库）**不响应 JS 合成的点击**：

```js
el.dispatchEvent(new MouseEvent('click', { bubbles: true }))  // ❌ 常常无效
el.click()                                                    // ❌ 常常无效
```

原因是它们监听的是浏览器**原生输入事件**（可信事件 `isTrusted === true`），
合成事件 `isTrusted === false`，会被直接忽略。

解法：先用 JS 拿到元素的**视口坐标**，再用 CDP 派发真实鼠标事件：

```js
// 第一步：取坐标
(function(){
  const el = document.querySelector('<css>');
  if (!el) return null;
  const r = el.getBoundingClientRect();
  return JSON.stringify({ x: Math.round(r.left + r.width/2), y: Math.round(r.top + r.height/2) });
})()
```

```
// 第二步：派发（双击 = 两组 press/release，第二组 clickCount=2）
Input.dispatchMouseEvent { type: mousePressed,  x, y, button: 'left', buttons: 1, clickCount: 1 }
Input.dispatchMouseEvent { type: mouseReleased, x, y, button: 'left', clickCount: 1 }
Input.dispatchMouseEvent { type: mousePressed,  x, y, button: 'left', buttons: 1, clickCount: 2 }
Input.dispatchMouseEvent { type: mouseReleased, x, y, button: 'left', clickCount: 2 }
```

`buttons: 1` 只在 `mousePressed` 时给（表示左键按住状态）。

> 坐标是**视口坐标**，元素必须已经在视口内。若元素在视口外，先 `el.scrollIntoView()` 再取坐标。

## 6. 直接执行 JS 片段：`Runtime.evaluate` 的写法模式

**IIFE 立即执行 + 返回 JSON 字符串**是最省事的模式：

```js
(() => {
  /* ... 采集逻辑 ... */
  return JSON.stringify({ /* 结构化结果 */ });
})()
```

为什么返回字符串而不是对象？因为 `returnByValue: true` 对复杂对象的序列化不稳定（循环引用、深度限制、`undefined` 字段丢失）。**返回 JSON 字符串，PowerShell 侧再 `ConvertFrom-Json`**，完全可控。

**需要 `await` 时**：表达式返回 Promise，并设 `awaitPromise: true`：

```js
(async () => { await new Promise(r => setTimeout(r, 2000)); return 'done'; })()
```

## 7. 等页面渲染就绪的模式

不要 `Start-Sleep` 猜时间，要**轮询关键元素**：

```powershell
for ($i = 0; $i -lt 30; $i++) {
  $probe = Get-CdpEvalValue -Ws $ws -CdpId $cdpId -Expr $probeExpr -TimeoutMs 15000
  if ($probe -and $probe -ne 'none') { break }
  Start-Sleep -Milliseconds 1500
}
```

就绪后**再额外等 2~2.5s**：容器出现了不等于内容渲染完了（异步取数、图表绘制、Mermaid 渲染都在之后）。
