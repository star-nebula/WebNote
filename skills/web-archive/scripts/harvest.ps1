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
  [ValidateSet('auto','dingtalk','feishu','generic')]
  [string]$Adapter = 'auto',
  [string]$ArticleSelector = "",
  [string]$OrderAttr = "",
  [string]$BlockIdAttr = "",
  [string]$BlockTypeAttr = "",
  [int]$Port = 9333,
  [int]$WaitMs = 1400,        # 单窗等待（懒加载），不得低于 1000
  [int]$StepRatioPct = 2,     # 滚动步长 = 容器高度 * 该百分比
  [int]$MinStepPx = 300,
  [int]$MaxWindows = 400,
  [int]$MaxStalledWindows = 3,
  [switch]$SingleView,
  [switch]$KeepTab
)

$ErrorActionPreference = 'Stop'
if ($WaitMs -lt 1000) { $WaitMs = 1000 }   # 采集礼貌：不低于 1s
$CdpPort = $Port

if ($Adapter -eq 'auto') {
  if ($Url -match 'alidocs\.dingtalk\.com') { $Adapter = 'dingtalk' }
  elseif ($Url -match 'feishu\.cn|feishu\.com|larksuite\.com') { $Adapter = 'feishu' }
  else { $Adapter = 'generic' }
}

if ([string]::IsNullOrWhiteSpace($BlockIdAttr)) {
  $BlockIdAttr = if ($Adapter -eq 'feishu') { 'data-block-id' } else { 'data-block-uuid' }
}
if ([string]::IsNullOrWhiteSpace($BlockTypeAttr)) {
  $BlockTypeAttr = if ($Adapter -eq 'feishu') { 'data-block-type' } else { 'data-type' }
}
if ([string]::IsNullOrWhiteSpace($ArticleSelector)) {
  $ArticleSelector = switch ($Adapter) {
    'feishu'  { '.docx-page-block, main, [role="main"], article, body' }
    'generic' { 'article, main, [role="main"], .doc-content, #content, body' }
    default   { 'article.body-editor-content, article' }
  }
}
if ([string]::IsNullOrWhiteSpace($OrderAttr) -and $Adapter -eq 'dingtalk') {
  $OrderAttr = 'data-cangjie-key'
}
Write-Host "[harvest] adapter=$Adapter blockId=$BlockIdAttr blockType=$BlockTypeAttr order=$OrderAttr"

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
  const BLOCK_ID_ATTR = __BLOCK_ID_ATTR__;
  const BLOCK_TYPE_ATTR = __BLOCK_TYPE_ATTR__;

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

  const blockId = el => el && el.getAttribute && el.getAttribute(BLOCK_ID_ATTR);
  const blockType = el => el && el.getAttribute && el.getAttribute(BLOCK_TYPE_ATTR);
  const isBlock = el => !!blockId(el);

  // 顶层块：祖先中没有其它「真块」（带 data-type）的块
  function topBlocks() {
    const all = Array.from(art.querySelectorAll('[' + BLOCK_ID_ATTR + ']'));
    return all.filter(b => {
      let p = b.parentElement;
      while (p && p !== art) { if (isBlock(p) && blockType(p)) return false; p = p.parentElement; }
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
          if (isBlock(n) && blockType(n)) return NodeFilter.FILTER_REJECT;
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
    const inner = Array.from(td.querySelectorAll('[' + BLOCK_ID_ATTR + ']')).filter(b => {
      let p = b.parentElement;
      while (p && p !== td) { if (isBlock(p) && blockType(p)) return false; p = p.parentElement; }
      return true;
    });
    if (inner.length) return inner.map(b => runsOf(b));
    return [runsOf(td)];
  }

  function mermaidSourceOf(el) {
    const candidates = [el, ...el.querySelectorAll('[data-mermaid-src], [data-mermaid], .mermaid, code.language-mermaid')];
    for (const node of candidates) {
      for (const attr of ['data-mermaid-src', 'data-mermaid', 'data-source']) {
        const value = node.getAttribute && node.getAttribute(attr);
        if (value && !/^data:image\//i.test(value)) return value;
      }
      if (node.matches && (node.matches('.mermaid') || node.matches('code.language-mermaid'))) {
        if (node.querySelector && node.querySelector('svg')) continue;
        const text = (node.innerText || '').trim();
        if (text && !/^<svg/i.test(text)) return text;
      }
    }
    return null;
  }

  function mermaidRenderOf(el) {
    const img = el.tagName && el.tagName.toLowerCase() === 'img' ? el : el.querySelector('img');
    const svg = img ? null : el.querySelector('svg');
    if (!img && !svg) return null;
    const src = img ? (img.getAttribute('src') || '') : '';
    const svgText = svg ? svg.outerHTML : '';
    let evidence = `${el.className || ''} ${el.getAttribute('data-type') || ''} ${img ? img.className || '' : ''} ${img ? img.alt || '' : ''} ${img ? img.title || '' : ''} ${img ? img.getAttribute('aria-label') || '' : ''} ${src} ${svg ? svgText.slice(0, 8000) : ''}`.toLowerCase();
    if (svg) return /mermaid|flowchart|sequencediagram|classdiagram|statediagram/.test(evidence)
      ? 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svgText)
      : null;
    try { evidence += ' ' + decodeURIComponent(src).slice(0, 8000).toLowerCase(); } catch (e) {}
    return /mermaid|flowchart|sequencediagram|classdiagram|statediagram/.test(evidence) ? src : null;
  }

  const tops = topBlocks();
  const blocks = [], tables = [];

  for (const b of tops) {
    let ty = blockType(b) || b.tagName.toLowerCase();
    ty = String(ty).toLowerCase().replace(/_/g, '-');
    const headingMatch = ty.match(/^heading-?(\d)$/);
    if (headingMatch) ty = 'heading-' + headingMatch[1];
    if (/^(text|paragraph|p)$/.test(ty)) ty = 'paragraph';
    if (/^(bullet|bullet-list|unordered-list|list)$/.test(ty)) ty = 'list-item';
    if (/^(ordered|ordered-list|number-list)$/.test(ty)) ty = 'list-item';

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
      u: blockId(b),
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
      if (a.name.startsWith('data-') && a.name !== BLOCK_ID_ATTR) entry.attrs[a.name] = a.value.substring(0, 80);
    }

    const mermaidSource = mermaidSourceOf(b);
    const mermaidRender = mermaidRenderOf(b);
    if (mermaidSource) {
      entry.ty = 'mermaid';
      entry.mermaid = mermaidSource;
      entry.text = mermaidSource;
    } else if (mermaidRender) {
      entry.ty = 'mermaid';
      entry.imgSrc = mermaidRender;
      entry.mermaidSourceMissing = true;
      entry.text = '[MERMAID_RENDERED_ONLY]';
    } else if (b.querySelector('table')) {
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
    } else if (b.getAttribute('data-language') || b.querySelector('[data-language]')) {
      const cb = b.getAttribute('data-language') ? b : b.querySelector('[data-language]');
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

$genericCollectJs = @'
(() => {
  const ART_SEL = __ART_SEL__;
  const ORDER_ATTR = __ORDER_ATTR__;
  const BLOCK_SELECTOR = 'h1,h2,h3,h4,h5,h6,p,li,blockquote,pre,table,hr,figure,img,.mermaid,[data-mermaid-src],[data-mermaid]';

  function findDoc() {
    for (const f of document.querySelectorAll('iframe')) {
      try {
        const d = f.contentDocument;
        if (d && d.querySelector('article, main, [role="main"], .doc-content, #content')) return d;
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

  const semanticBlocks = Array.from(art.querySelectorAll(BLOCK_SELECTOR)).filter(el => {
    if (el === art) return false;
    let p = el.parentElement;
    while (p && p !== art) {
      if (p.matches && p.matches(BLOCK_SELECTOR)) return false;
      p = p.parentElement;
    }
    return true;
  });

  function stableId(el) {
    for (const attr of ['data-block-id', 'data-block-uuid', 'id']) {
      const value = el.getAttribute && el.getAttribute(attr);
      if (value) return attr + ':' + value;
    }
    const path = [];
    let node = el;
    while (node && node !== art) {
      const parent = node.parentElement;
      if (!parent) break;
      path.unshift(Array.prototype.indexOf.call(parent.children, node));
      node = parent;
    }
    return 'dom:' + path.join('.');
  }

  function pushedRuns(el) {
    const runs = [];
    let current = null;
    const walker = doc.createTreeWalker(el, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT, {
      acceptNode(node) {
        if (node.nodeType === Node.TEXT_NODE) return NodeFilter.FILTER_ACCEPT;
        if (node.nodeType !== Node.ELEMENT_NODE) return NodeFilter.FILTER_REJECT;
        if (node.matches && node.matches(BLOCK_SELECTOR)) {
          // Paragraphs nested in quotes/table cells are part of the selected block,
          // not separate top-level knowledge blocks.
          if (node.tagName === 'P') {
            if (current) { runs.push(current); current = null; }
            if (runs.length && !runs[runs.length - 1].br) runs.push({ br: 1 });
            return NodeFilter.FILTER_ACCEPT;
          }
          return NodeFilter.FILTER_REJECT;
        }
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    while (walker.nextNode()) {
      const node = walker.currentNode;
      if (node.nodeType === Node.ELEMENT_NODE) {
        if (node.tagName === 'BR') {
          if (current) { runs.push(current); current = null; }
          runs.push({ br: 1 });
        } else if (node.tagName === 'IMG') {
          if (current) { runs.push(current); current = null; }
          runs.push({ img: node.getAttribute('src') || '' });
        }
        continue;
      }
      let bold = false, code = false, italic = false, strike = false;
      for (let p = node.parentElement; p && p !== el.parentElement; p = p.parentElement) {
        if (p.tagName === 'CODE') code = true;
        if (p.tagName === 'STRONG' || p.tagName === 'B') bold = true;
        if (p.tagName === 'EM' || p.tagName === 'I') italic = true;
        if (p.tagName === 'S' || p.tagName === 'DEL') strike = true;
        const style = p.style;
        if (style) {
          const weight = style.fontWeight;
          if (weight === 'bold' || weight === 'bolder' || (parseInt(weight) >= 600 && parseInt(weight) <= 900)) bold = true;
          if (style.fontStyle === 'italic') italic = true;
          if (String(style.textDecorationLine || style.textDecoration || '').includes('line-through')) strike = true;
        }
      }
      const key = `${bold}|${code}|${italic}|${strike}`;
      const text = node.textContent;
      if (current && current._k === key) current.t += text;
      else {
        if (current) runs.push(current);
        current = { t: text, b: bold, c: code, _k: key };
        if (italic) current.i = 1;
        if (strike) current.s = 1;
      }
    }
    if (current) runs.push(current);
    return runs;
  }

  function mermaidSourceOf(el) {
    const candidates = [el, ...el.querySelectorAll('[data-mermaid-src], [data-mermaid], .mermaid, code.language-mermaid')];
    for (const node of candidates) {
      for (const attr of ['data-mermaid-src', 'data-mermaid', 'data-source']) {
        const value = node.getAttribute && node.getAttribute(attr);
        if (value && !/^data:image\//i.test(value)) return value;
      }
      if (node.matches && (node.matches('.mermaid') || node.matches('code.language-mermaid'))) {
        if (node.querySelector && node.querySelector('svg')) continue;
        const text = (node.innerText || '').trim();
        if (text && !/^<svg/i.test(text)) return text;
      }
    }
    return null;
  }

  function mermaidRenderOf(el) {
    const img = el.tagName && el.tagName.toLowerCase() === 'img' ? el : el.querySelector('img');
    const svg = img ? null : el.querySelector('svg');
    if (!img && !svg) return null;
    const src = img ? (img.getAttribute('src') || '') : '';
    const svgText = svg ? svg.outerHTML : '';
    let evidence = `${el.className || ''} ${el.getAttribute('data-type') || ''} ${img ? img.className || '' : ''} ${img ? img.alt || '' : ''} ${img ? img.title || '' : ''} ${img ? img.getAttribute('aria-label') || '' : ''} ${src} ${svg ? svgText.slice(0, 8000) : ''}`.toLowerCase();
    if (svg) return /mermaid|flowchart|sequencediagram|classdiagram|statediagram/.test(evidence)
      ? 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svgText)
      : null;
    try { evidence += ' ' + decodeURIComponent(src).slice(0, 8000).toLowerCase(); } catch (e) {}
    return /mermaid|flowchart|sequencediagram|classdiagram|statediagram/.test(evidence) ? src : null;
  }

  const blocks = [], tables = [];
  for (const el of semanticBlocks) {
    const tag = el.tagName.toLowerCase();
    let ty = tag;
    if (/^h[1-6]$/.test(tag)) ty = 'heading-' + tag.slice(1);
    else if (tag === 'p') ty = 'paragraph';
    else if (tag === 'li') ty = 'list-item';
    else if (tag === 'blockquote') ty = 'quote';
    else if (tag === 'pre') ty = 'codeblock';
    else if (tag === 'table') ty = 'table';
    else if (tag === 'hr') ty = 'hr';
    else if (tag === 'img' || tag === 'figure') ty = 'image';

    const entry = {
      u: stableId(el), k: ORDER_ATTR ? parseInt(el.getAttribute(ORDER_ATTR) || '-1') : -1, ty,
      q: !!(el.closest && el.closest('blockquote')), li: null, ind: 0, attrs: {}, runs: null, text: null
    };
    for (const attr of el.attributes) {
      if (attr.name.startsWith('data-')) entry.attrs[attr.name] = attr.value.substring(0, 120);
    }

    const mermaid = mermaidSourceOf(el);
    const mermaidRendered = mermaidRenderOf(el);
    if (mermaid) {
      entry.ty = 'mermaid'; entry.mermaid = mermaid; entry.text = mermaid;
    } else if (mermaidRendered) {
      entry.ty = 'mermaid'; entry.imgSrc = mermaidRendered; entry.mermaidSourceMissing = true; entry.text = '[MERMAID_RENDERED_ONLY]';
    } else if (ty === 'table') {
      const table = el.querySelector('table') || el;
      const rows = [];
      for (const tr of table.rows) {
        const cells = [];
        for (const td of tr.cells) {
          cells.push({ cs: td.colSpan || 1, rs: td.rowSpan || 1, runs: [pushedRuns(td)] });
        }
        rows.push(cells);
      }
      entry.trow = rows.length; entry.text = `[TABLE ${rows.length}r]`;
      tables.push({ u: entry.u, k: entry.k, rows });
    } else if (ty === 'codeblock') {
      const code = el.querySelector('code') || el;
      const className = `${el.className || ''} ${code.className || ''}`;
      const langMatch = className.match(/language-([A-Za-z0-9_+.#-]+)/);
      entry.lang = el.getAttribute('data-language') || code.getAttribute('data-language') || (langMatch ? langMatch[1] : '');
      entry.lines = (code.innerText || '').replace(/^\s*\d+\s*$/gm, '').split(/\r?\n/);
      entry.text = entry.lines.join('\n');
    } else if (ty === 'image') {
      const img = el.tagName.toLowerCase() === 'img' ? el : el.querySelector('img');
      entry.voidType = 'image'; entry.imgSrc = img ? (img.getAttribute('src') || '') : '';
      entry.text = '[image]';
    } else if (ty === 'hr') {
      entry.voidType = 'hr'; entry.text = '[hr]';
    } else {
      entry.runs = pushedRuns(el);
      entry.text = entry.runs.map(run => run.t || (run.img ? '[IMG]' : run.br ? '\n' : '')).join('');
    }

    if (ty === 'list-item') {
      const list = el.closest('ul,ol');
      if (list && list.tagName === 'OL') {
        const items = Array.from(list.children).filter(child => child.tagName === 'LI');
        const start = parseInt(list.getAttribute('start') || '1');
        entry.li = (start + items.indexOf(el)) + '.';
      } else {
        entry.li = '•';
      }
      let depth = 0;
      for (let p = el.parentElement; p && p !== art; p = p.parentElement) if (p.matches && p.matches('ul,ol')) depth++;
      entry.ind = depth * 12;
    }
    blocks.push(entry);
  }

  let scroll = null;
  for (const div of doc.querySelectorAll('div,main')) {
    if (div.scrollHeight - div.clientHeight > 500 && div.clientHeight > 300) {
      if (!scroll || div.scrollHeight > scroll.scrollHeight) scroll = div;
    }
  }
  const geo = scroll ? { top: Math.round(scroll.scrollTop), h: scroll.scrollHeight, ch: scroll.clientHeight } : null;
  return JSON.stringify({ geo, blocks, tables, adapter: 'generic' });
})()
'@

$artSelJson = ConvertTo-Json -InputObject @($ArticleSelector -split ',' | ForEach-Object { $_.Trim() }) -Compress
if ($Adapter -eq 'generic') {
  $collectJs = $genericCollectJs.Replace('__ART_SEL__', $artSelJson)
  $collectJs = $collectJs.Replace('__ORDER_ATTR__', "'" + $OrderAttr + "'")
} else {
  $collectJs = $collectJs.Replace('__ART_SEL__', $artSelJson)
  $collectJs = $collectJs.Replace('__ORDER_ATTR__', "'" + $OrderAttr + "'")
  $collectJs = $collectJs.Replace('__BLOCK_ID_ATTR__', "'" + $BlockIdAttr + "'")
  $collectJs = $collectJs.Replace('__BLOCK_TYPE_ATTR__', "'" + $BlockTypeAttr + "'")
}

# 滚动 JS：滚动到指定位置的滚动容器
$scrollJs = @'
(pos) => {
  function findDoc() {
    const frames = document.querySelectorAll('iframe');
    for (const f of frames) {
      try {
        const d = f.contentDocument;
        if (d && d.querySelector('article, main, [role="main"], .doc-content, #content')) return d;
      } catch (e) {}
    }
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
$initialLoginProbe = Get-CdpEvalValue -Ws $ws -CdpId $cdpId -Expr "(/login|passport|sso/i.test(location.href) || !!document.querySelector('input[type=password]')) ? 'login' : 'none'" -TimeoutMs 10000
if ($initialLoginProbe -eq 'login') {
  Write-Host "[harvest] ERROR: login-required。请复用用户已有登录态，或在可见浏览器中手动完成登录后重试。"
  $ws.Dispose()
  exit 2
}
$ready = $false
$artSelFirst = ($ArticleSelector -split ',')[0].Trim()
$probeExpr = @"
(function(){
  const sels = $artSelJson;
  const frames = document.querySelectorAll('iframe');
  for (const f of frames) {
    try {
      const d = f.contentDocument;
      if (d && sels.some(s => d.querySelector(s))) return 'frame-ok';
    } catch(e){}
  }
  return sels.some(s => document.querySelector(s)) ? 'doc-ok' : 'none';
})()
"@
for ($i = 0; $i -lt 30; $i++) {
  $probe = Get-CdpEvalValue -Ws $ws -CdpId $cdpId -Expr $probeExpr -TimeoutMs 15000
  if ($probe -and $probe -ne 'none') { $ready = $true; Write-Host "[harvest] ready ($probe) after $($i+1) polls"; break }
  $loginProbe = Get-CdpEvalValue -Ws $ws -CdpId $cdpId -Expr "(/login|passport|sso/i.test(location.href) || !!document.querySelector('input[type=password]')) ? 'login' : 'none'" -TimeoutMs 10000
  if ($loginProbe -eq 'login') {
    Write-Host "[harvest] ERROR: login-required。请复用用户已有登录态，或在可见浏览器中手动完成登录后重试。"
    $ws.Dispose()
    exit 2
  }
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
$stalled = 0
$lastSignature = ''
$lastTop = -1
while ($true) {
  $win++
  $sr = Get-CdpEvalValue -Ws $ws -CdpId $cdpId -Expr "(($scrollJs)($pos))" -TimeoutMs 20000
  if (-not $sr) { Start-Sleep -Milliseconds 900; $sr = Get-CdpEvalValue -Ws $ws -CdpId $cdpId -Expr "(($scrollJs)($pos))" -TimeoutMs 20000 }
  Start-Sleep -Milliseconds $WaitMs

  $data = Get-CdpEvalValue -Ws $ws -CdpId $cdpId -Expr $collectJs -TimeoutMs 60000
  if (-not $data) { Start-Sleep -Milliseconds 1500; $data = Get-CdpEvalValue -Ws $ws -CdpId $cdpId -Expr $collectJs -TimeoutMs 60000 }
  if (-not $data) {
    $stalled++
    Write-Host "[harvest] WARN win $win 抽取为空，连续空窗 $stalled/$MaxStalledWindows"
    if ($SingleView) { break }
    if ($stalled -ge $MaxStalledWindows) { Write-Host "[harvest] ERROR 连续空抽取，停止以避免无限循环"; break }
    continue
  }

  $obj = $data | ConvertFrom-Json
  $blockIndex = 0
  foreach ($block in @($obj.blocks)) {
    $block | Add-Member -NotePropertyName w -NotePropertyValue $win -Force
    $block | Add-Member -NotePropertyName i -NotePropertyValue $blockIndex -Force
    $blockIndex++
  }
  $data = $obj | ConvertTo-Json -Depth 16 -Compress

  $file = Join-Path $OutDir ("{0}_w{1}.json" -f $Prefix, $win)
  [System.IO.File]::WriteAllText($file, $data, [System.Text.Encoding]::UTF8)
  $files += $file

  $nb = @($obj.blocks).Count
  $top = if ($obj.geo) { [int]$obj.geo.top } else { -1 }
  $h = if ($obj.geo) { [int]$obj.geo.h } else { 0 }
  $ch = if ($obj.geo) { [int]$obj.geo.ch } else { 0 }
  $geoTxt = if ($obj.geo) { "top=$top/$h ch=$ch" } else { 'nosc' }
  Write-Host ("[harvest] w{0} {1} blocks={2}" -f $win, $geoTxt, $nb)

  $signature = (@($obj.blocks) | ForEach-Object { [string]$_.u }) -join '|'
  if ($nb -eq 0) {
    $stalled++
  } elseif ($signature -eq $lastSignature) {
    $stalled++
  } else {
    $stalled = 0
  }
  $lastSignature = $signature
  $lastTop = $top

  if ($SingleView) { break }
  if ($stalled -ge $MaxStalledWindows) {
    Write-Host "[harvest] WARN 连续 $stalled 窗无新内容，停止采集"
    break
  }
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
