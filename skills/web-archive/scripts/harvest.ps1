<#
.SYNOPSIS
  分窗滚动采集器 —— 网页拓存的核心。

.DESCRIPTION
  为什么必须分窗？长文档页（云文档、虚拟滚动列表）滚出视口的块会被卸载，
  一次性 innerText 只能拿到当前视口。所以：

    找滚动容器 -> 记录几何 -> 逐窗滚动 -> 每窗抽取全部顶层块 -> 落盘
    -> 直到 scrollTop + clientHeight >= scrollHeight

  滚动步长取容器高度的 2%（最小 300px）—— 步长太大会漏块，太小则慢。

  抽取「顶层块」而非 innerText，是为了保住块级结构：
    - 标题级别、列表符号与缩进、引用、表格（含合并单元格）、代码块（含语言）
    - 行内样式（加粗常在 inline style.fontWeight 而非 <strong>）
    - 图片 / 分割线 / void 块

.PARAMETER ArticleSelector
  正文容器 CSS 选择器。默认命中钉钉云文档：
    'article.body-editor-content', 'article'
  其他站点先用 probe-dom.js 探明再覆盖。

.PARAMETER OrderAttr
  块顺序属性名。钉钉云文档用 data-cangjie-key（真实阅读顺序）。
  留空则按 DOM 出现顺序。

.EXAMPLE
  powershell -File harvest.ps1 -Url "https://alidocs.dingtalk.com/i/nodes/XXXX" -Prefix doc1

.EXAMPLE
  # 短页面：不滚动，单窗即止
  powershell -File harvest.ps1 -Url "https://news.example.com/a" -Prefix news1 -SingleView
#>
param(
  [Parameter(Mandatory=$true)][string]$Url,
  [Parameter(Mandatory=$true)][string]$Prefix,
  [string]$OutDir = "",
  [string]$ArticleSelector = "article.body-editor-content, article",
  [string]$OrderAttr = "data-cangjie-key",
  [int]$Port = 9333,
  [int]$WaitMs = 1400,        # 单窗等待（懒加载），不得低于 1000
  [int]$StepRatioPct = 2,     # 滚动步长 = 容器高度 * 该百分比
  [int]$MinStepPx = 300,
  [int]$MaxWindows = 400,
  [switch]$SingleView,
  [switch]$KeepTab
)

$ErrorActionPreference = 'Stop'
if ($WaitMs -lt 1000) { $WaitMs = 1000 }   # 采集礼貌：不低于 1s
$CdpPort = $Port

if ([string]::IsNullOrWhiteSpace($OutDir)) { $OutDir = Join-Path $PSScriptRoot '..\work' }
if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Path $OutDir -Force | Out-Null }
$OutDir = (Resolve-Path $OutDir).Path

# ---------- CDP 底座（复用 cdp.ps1 的函数） ----------
. (Join-Path $PSScriptRoot 'cdp.ps1') -Port $CdpPort

# ---------- 注入站点参数，生成抽取 JS ----------
$collectJs = @'
(() => {
  const ART_SEL = __ART_SEL__;
  const ORDER_ATTR = __ORDER_ATTR__;

  function findDoc() {
    const frames = document.querySelectorAll('iframe');
    for (const f of frames) {
      try {
        const d = f.contentDocument;
        if (d && d.querySelector('article')) return d;
      } catch (e) {}
    }
    return document;
  }
  const doc = findDoc();

  let art = null;
  for (const s of ART_SEL) {
    const el = doc.querySelector(s);
    if (el) { art = el; break; }
  }
  if (!art) return JSON.stringify({ err: 'no-article' });

  const isBlock = el => el && el.getAttribute && el.getAttribute('data-block-uuid');

  // 顶层块：祖先中没有其它「真块」（带 data-type）的块
  function topBlocks() {
    const all = Array.from(art.querySelectorAll('[data-block-uuid]'));
    return all.filter(b => {
      let p = b.parentElement;
      while (p && p !== art) { if (isBlock(p) && p.getAttribute('data-type')) return false; p = p.parentElement; }
      return true;
    });
  }

  // 把一个元素拆成「行内 run」序列，保留粗/斜/删/行内代码/图片/换行
  function runsOf(el) {
    const runs = [];
    const walker = doc.createTreeWalker(el, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT, {
      acceptNode(n) {
        if (n.nodeType === 3) return NodeFilter.FILTER_ACCEPT;
        if (n.nodeType === 1) {
          const tag = n.tagName;
          if (tag === 'CODE' || tag === 'IMG' || tag === 'BR') return NodeFilter.FILTER_ACCEPT;
          if (isBlock(n) && n.getAttribute('data-type')) return NodeFilter.FILTER_REJECT;
          return NodeFilter.FILTER_ACCEPT;
        }
        return NodeFilter.FILTER_REJECT;
      }
    });
    let cur = null;
    while (walker.nextNode()) {
      const n = walker.currentNode;
      if (n.nodeType === 1) {
        if (n.tagName === 'BR') { if (cur) { runs.push(cur); cur = null; } runs.push({ br: 1 }); continue; }
        if (n.tagName === 'IMG') {
          if (cur) { runs.push(cur); cur = null; }
          runs.push({ img: n.getAttribute('src') || '' });
          continue;
        }
        continue;
      }
      // 文本节点：向上探父链，判定行内样式
      let bold = false, code = false, ital = false, strike = false;
      let p = n.parentElement;
      while (p && p !== el.parentElement) {
        if (p.tagName === 'CODE') code = true;
        if (p.tagName === 'STRONG' || p.tagName === 'B') bold = true;
        if (p.tagName === 'EM' || p.tagName === 'I') ital = true;
        if (p.tagName === 'S' || p.tagName === 'DEL') strike = true;
        const st = p.style;
        if (st) {
          const fw = st.fontWeight;
          if (fw === 'bold' || fw === 'bolder' || (parseInt(fw) >= 600 && parseInt(fw) <= 900)) bold = true;
          if (st.fontStyle === 'italic') ital = true;
          const td = st.textDecorationLine || st.textDecoration || '';
          if (String(td).indexOf('line-through') >= 0) strike = true;
        }
        p = p.parentElement;
      }
      const t = n.textContent;
      const key = bold + '|' + code + '|' + ital + '|' + strike;
      if (cur && cur._k === key) cur.t += t;
      else { if (cur) runs.push(cur); cur = { t: t, b: bold, c: code, _k: key }; if (ital) cur.i = 1; if (strike) cur.s = 1; }
    }
    if (cur) runs.push(cur);
    return runs;
  }

  // 表格单元格：只取该 td 内的顶层块（避免把嵌套块的文字重复计入）
  function cellRuns(td) {
    const inner = Array.from(td.querySelectorAll('[data-block-uuid]')).filter(b => {
      let p = b.parentElement;
      while (p && p !== td) { if (isBlock(p) && p.getAttribute('data-type')) return false; p = p.parentElement; }
      return true;
    });
    if (inner.length) return inner.map(b => runsOf(b));
    return [runsOf(td)];
  }

  const tops = topBlocks();
  const blocks = [], tables = [];

  for (const b of tops) {
    const ty = b.getAttribute('data-type') || b.tagName.toLowerCase();

    // 列表识别：祖先里有 group-list-container，则取符号与缩进
    let li = null, ind = 0;
    const pp = b.parentElement;
    if (pp) {
      const lc = (pp.getAttribute && pp.getAttribute('data-testid') === 'group-list-container')
        ? pp : (pp.closest ? pp.closest('[data-testid="group-list-container"]') : null);
      if (lc) {
        const sym = lc.querySelector('span[data-testid="list-symbol"]');
        li = sym ? sym.textContent : '?';
        const pl = lc.style && lc.style.paddingLeft ? parseInt(lc.style.paddingLeft) : 0;
        ind = isNaN(pl) ? 0 : pl;
      }
    }

    const orderRaw = ORDER_ATTR ? b.getAttribute(ORDER_ATTR) : null;
    const entry = {
      u: b.getAttribute('data-block-uuid'),
      k: orderRaw === null ? -1 : parseInt(orderRaw || '-1'),
      ty: ty,
      q: (b.parentElement && b.parentElement.tagName === 'BLOCKQUOTE') ? 1 : 0,
      li: li,
      ind: ind,
      attrs: {},
      runs: null,
      text: null
    };
    for (const a of b.attributes) {
      if (a.name.startsWith('data-') && a.name !== 'data-block-uuid') entry.attrs[a.name] = a.value.substring(0, 80);
    }

    if (b.querySelector('table')) {
      const tb = b.querySelector('table');
      const rows = [];
      for (const tr of tb.rows) {
        const cells = [];
        for (const td of tr.cells) {
          cells.push({
            cs: td.colSpan || 1,
            rs: td.rowSpan || 1,
            runs: cellRuns(td)
          });
        }
        rows.push(cells);
      }
      entry.ty = 'table';
      entry.trow = rows.length;
      tables.push({ u: entry.u, k: entry.k, rows: rows });
      entry.text = '[TABLE ' + rows.length + 'r]';
    } else if (b.querySelector('[data-language]')) {
      const cb = b.querySelector('[data-language]');
      entry.ty = 'codeblock';
      entry.lang = cb.getAttribute('data-language') || '';
      const lineEls = cb.querySelectorAll('[class*="line"], .cm-line');
      entry.lines = lineEls.length ? Array.from(lineEls).map(l => l.innerText) : [cb.innerText];
      entry.text = entry.lines.join('\n');
    } else {
      // void 块：分割线 / 图片 / 其他原子块
      if (b.getAttribute('data-cangjie-void') === 'true') {
        const innerTyped = b.querySelector('[data-type]');
        entry.voidType = innerTyped ? innerTyped.getAttribute('data-type') : 'unknown';
        const vim = b.querySelector('img');
        if (vim) entry.imgSrc = (vim.getAttribute('src') || '').substring(0, 400);
        entry.text = '[' + entry.voidType + ']';
      }
      entry.runs = runsOf(b);
      if (entry.text === null) {
        entry.text = entry.runs.map(r => r.t || (r.img ? '[IMG]' : (r.br ? '\n' : ''))).join('');
      }
    }
    blocks.push(entry);
  }

  // 滚动容器：最大的、真正可滚的 div
  let sc = null;
  for (const d of doc.querySelectorAll('div')) {
    if (d.scrollHeight - d.clientHeight > 500 && d.clientHeight > 300) {
      if (!sc || d.scrollHeight > sc.scrollHeight) sc = d;
    }
  }
  const geo = sc ? { top: Math.round(sc.scrollTop), h: sc.scrollHeight, ch: sc.clientHeight } : null;
  return JSON.stringify({ geo: geo, blocks: blocks, tables: tables });
})()
'@

$artSelJson = ConvertTo-Json -InputObject @($ArticleSelector -split ',' | ForEach-Object { $_.Trim() }) -Compress
$collectJs = $collectJs.Replace('__ART_SEL__', $artSelJson)
$collectJs = $collectJs.Replace('__ORDER_ATTR__', "'" + $OrderAttr + "'")

# 滚动 JS：滚动到指定位置的滚动容器
$scrollJs = @'
(pos) => {
  function findDoc() {
    const frames = document.querySelectorAll('iframe');
    for (const f of frames) { try { const d = f.contentDocument; if (d && d.querySelector('article')) return d; } catch (e) {} }
    return document;
  }
  const doc = findDoc();
  let sc = null;
  for (const d of doc.querySelectorAll('div')) {
    if (d.scrollHeight - d.clientHeight > 500 && d.clientHeight > 300) {
      if (!sc || d.scrollHeight > sc.scrollHeight) sc = d;
    }
  }
  if (!sc) return JSON.stringify({ err: 'no-sc' });
  sc.scrollTop = pos;
  sc.dispatchEvent(new Event('scroll'));
  return JSON.stringify({ ok: 1, top: Math.round(sc.scrollTop), h: sc.scrollHeight, ch: sc.clientHeight });
}
'@

# ---------- 开/复用标签页 ----------
$tab = $null
foreach ($t in (Get-CdpTargets $CdpPort | Where-Object { $_.type -eq 'page' })) {
  if ($t.url -and $Url -like "*$($t.url)*") { $tab = $t; break }
}
$created = $false
if (-not $tab) {
  # 用 URL 的路径尾部做匹配键，避免同域不同文档复用错标签页
  $key = ($Url -split '/')[-1]
  $tab = (Get-CdpTargets $CdpPort | Where-Object { $_.type -eq 'page' -and $_.url -like "*$key*" } | Select-Object -First 1)
}
if (-not $tab) {
  $enc = [Uri]::EscapeDataString($Url)
  $tab = Invoke-RestMethod -Uri "http://127.0.0.1:$CdpPort/json/new?$enc" -Method Put -TimeoutSec 20
  $created = $true
  Start-Sleep -Seconds 5
}
Write-Host "[harvest] tab id=$($tab.id)"
$ws = Connect-CdpWs $tab.webSocketDebuggerUrl
$cdpId = [ref]1

# ---------- 等正文渲染 ----------
$ready = $false
$artSelFirst = ($ArticleSelector -split ',')[0].Trim()
$probeExpr = @"
(function(){
  const sels = '$artSelFirst';
  const frames = document.querySelectorAll('iframe');
  for (const f of frames) { try { if (f.contentDocument && f.contentDocument.querySelector(sels)) return 'frame-ok'; } catch(e){} }
  return document.querySelector(sels) ? 'doc-ok' : 'none';
})()
"@
for ($i = 0; $i -lt 30; $i++) {
  $probe = Get-CdpEvalValue -Ws $ws -CdpId $cdpId -Expr $probeExpr -TimeoutMs 15000
  if ($probe -and $probe -ne 'none') { $ready = $true; Write-Host "[harvest] ready ($probe) after $($i+1) polls"; break }
  Start-Sleep -Milliseconds 1500
}
if (-not $ready) {
  Write-Host "[harvest] ERROR: 正文容器 '$artSelFirst' 未渲染。可能要登录 / 选择器不对 / 页面结构不同 —— 先跑 probe-dom.js。"
  $ws.Dispose(); exit 1
}
Start-Sleep -Milliseconds 2500

# ---------- 分窗循环 ----------
$win = 0
$pos = 0
$files = @()
while ($true) {
  $win++
  $sr = Get-CdpEvalValue -Ws $ws -CdpId $cdpId -Expr "(($scrollJs)($pos))" -TimeoutMs 20000
  if (-not $sr) { Start-Sleep -Milliseconds 900; $sr = Get-CdpEvalValue -Ws $ws -CdpId $cdpId -Expr "(($scrollJs)($pos))" -TimeoutMs 20000 }
  Start-Sleep -Milliseconds $WaitMs

  $data = Get-CdpEvalValue -Ws $ws -CdpId $cdpId -Expr $collectJs -TimeoutMs 60000
  if (-not $data) { Start-Sleep -Milliseconds 1500; $data = Get-CdpEvalValue -Ws $ws -CdpId $cdpId -Expr $collectJs -TimeoutMs 60000 }
  if (-not $data) {
    Write-Host "[harvest] WARN win $win 抽取为空，跳过"
    if ($SingleView) { break }
    continue
  }

  $file = Join-Path $OutDir ("{0}_w{1}.json" -f $Prefix, $win)
  [System.IO.File]::WriteAllText($file, $data, [System.Text.Encoding]::UTF8)
  $files += $file

  $obj = $data | ConvertFrom-Json
  $nb = @($obj.blocks).Count
  $top = if ($obj.geo) { [int]$obj.geo.top } else { -1 }
  $h = if ($obj.geo) { [int]$obj.geo.h } else { 0 }
  $ch = if ($obj.geo) { [int]$obj.geo.ch } else { 0 }
  $geoTxt = if ($obj.geo) { "top=$top/$h ch=$ch" } else { 'nosc' }
  Write-Host ("[harvest] w{0} {1} blocks={2}" -f $win, $geoTxt, $nb)

  if ($SingleView) { break }
  if ($top -ge 0 -and ($top + $ch) -ge ($h - 10)) { break }   # 到底
  $step = [Math]::Max($MinStepPx, [int]($h * $StepRatioPct / 100.0))
  $pos += $step
  if ($pos -ge $h) { break }
  if ($win -ge $MaxWindows) { Write-Host "[harvest] WARN 达到窗口上限 $MaxWindows，可能在无限滚动"; break }
}

Write-Host "[harvest] DONE $Prefix windows=$win files=$($files.Count) -> $OutDir"
if ($created -and -not $KeepTab) {
  [void](Invoke-RestMethod -Uri "http://127.0.0.1:$CdpPort/json/close/$($tab.id)" -Method Get -TimeoutSec 10 -ErrorAction SilentlyContinue)
}
$ws.Dispose()
