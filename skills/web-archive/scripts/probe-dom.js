/*
 * DOM 探针 —— 面对新站点时，先跑这个，别急着开采。
 *
 * 作用：打印「块类型统计 + 结构样本 + 滚动几何」，用来回答三个问题：
 *   1. 正文容器是谁？（直接找 article？还是在 iframe 里？）
 *   2. 块模型是什么？（有没有 data-block-uuid / data-type 这类块级标记？）
 *   3. 滚动容器是谁？（懒加载长文档必须找准它）
 *
 * 用法：powershell -File cdp.ps1 -JsFile probe-dom.js -UrlMatch "<url 关键字>"
 */
(() => {
  // ---- 1. 找正文文档（可能在同源 iframe 内）----
  function findDoc() {
    const frames = document.querySelectorAll('iframe');
    for (const f of frames) {
      try {
        const d = f.contentDocument;
        if (d && (d.querySelector('article') || d.querySelector('[data-block-uuid]'))) {
          return { doc: d, inFrame: true };
        }
      } catch (e) { /* 跨域 iframe 读不到 contentDocument，正常 */ }
    }
    return { doc: document, inFrame: false };
  }
  const ctx = findDoc();
  const doc = ctx.doc;

  // ---- 2. 找正文容器（逐级降级）----
  const ART_SELECTORS = [
    'article.body-editor-content',
    'article',
    '[data-block-uuid]',
    'main',
    '[role="main"]',
    '.doc-content',
    '#content'
  ];
  let art = null, artSel = null;
  for (const s of ART_SELECTORS) {
    const el = doc.querySelector(s);
    if (el) { art = el; artSel = s; break; }
  }

  const out = {
    url: location.href,
    title: document.title,
    inFrame: ctx.inFrame,
    iframeCount: document.querySelectorAll('iframe').length,
    articleSelector: artSel,
    articleFound: !!art
  };

  if (!art) {
    out.hint = '未找到正文容器。可能：内容尚未渲染（先等待/滚动）、在跨域 iframe 内、或需要登录。';
    return JSON.stringify(out, null, 1);
  }

  // ---- 3. 块模型统计 ----
  const blockSel = '[data-block-uuid]';
  const allBlocks = Array.from(art.querySelectorAll(blockSel));
  out.hasBlockModel = allBlocks.length > 0;
  out.totalMatchedBlocks = allBlocks.length;

  // 顶层块 = 祖先里没有别的「真块」（有 data-type 的才算真块）
  const isRealBlock = el => el && el.getAttribute && el.getAttribute('data-type');
  const tops = allBlocks.filter(b => {
    let p = b.parentElement;
    while (p && p !== art) {
      if (isRealBlock(p)) return false;
      p = p.parentElement;
    }
    return true;
  });
  out.topLevelBlocks = tops.length;

  const stats = {};
  for (const b of tops) {
    const t = b.getAttribute('data-type') || b.tagName.toLowerCase();
    stats[t] = (stats[t] || 0) + 1;
  }
  out.typeStats = stats;

  // 属性名清单（看有没有顺序键 / 语言 / void 标记）
  const attrNames = new Set();
  for (const b of tops.slice(0, 60)) {
    for (const a of b.attributes) {
      if (a.name.startsWith('data-')) attrNames.add(a.name);
    }
  }
  out.dataAttrsSeen = Array.from(attrNames).sort();

  // 行内样式来源（加粗常常靠 inline style 而非 <strong>）
  out.inlineStyleTags = {
    strong: art.querySelectorAll('strong, b').length,
    em: art.querySelectorAll('em, i').length,
    code: art.querySelectorAll('code').length,
    spans: art.querySelectorAll('span').length
  };

  // 特殊结构存在性
  out.specials = {
    tables: art.querySelectorAll('table').length,
    images: art.querySelectorAll('img').length,
    codeContainers: art.querySelectorAll('[data-language], pre').length,
    hrs: art.querySelectorAll('hr').length,
    listContainers: art.querySelectorAll('[data-testid="group-list-container"]').length
  };

  // ---- 4. 结构样本（各取一个，看清真实 DOM 形状）----
  const samples = {};
  function sample(name, pred, maxLen) {
    const b = tops.find(pred);
    if (b) samples[name] = b.outerHTML.substring(0, maxLen || 900);
  }
  sample('heading', b => /heading|title/i.test(b.getAttribute('data-type') || ''), 700);
  sample('paragraph', b => (b.getAttribute('data-type') || '') === 'paragraph', 700);
  sample('list', b => {
    const p = b.parentElement;
    return !!(p && p.closest && p.closest('[data-testid="group-list-container"]'));
  }, 700);
  sample('quote', b => b.parentElement && b.parentElement.tagName === 'BLOCKQUOTE', 700);
  sample('code', b => b.querySelector('[data-language]'), 700);
  sample('table', b => b.querySelector('table'), 900);
  sample('image', b => b.querySelector('img'), 500);
  out.samples = samples;

  // ---- 5. 滚动容器几何（懒加载判定的依据）----
  let sc = null;
  for (const d of doc.querySelectorAll('div')) {
    if (d.scrollHeight - d.clientHeight > 500 && d.clientHeight > 300) {
      if (!sc || d.scrollHeight > sc.scrollHeight) sc = d;
    }
  }
  out.scroll = sc
    ? { scrollHeight: sc.scrollHeight, clientHeight: sc.clientHeight,
        scrollTop: Math.round(sc.scrollTop), className: (sc.className || '').toString().substring(0, 80) }
    : null;
  out.needsWindowedHarvest = !!(sc && sc.scrollHeight > sc.clientHeight * 1.5);

  return JSON.stringify(out, null, 1);
})()
