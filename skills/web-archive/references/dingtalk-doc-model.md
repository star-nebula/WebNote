# 钉钉云文档 DOM 块模型（alidocs）

针对 `https://alidocs.dingtalk.com/i/nodes/<NODE>` 这类钉钉云文档（内部渲染引擎代号 **cangjie**）。
这是本方案打磨最深的一个站点，模型清晰、可完全结构化还原。

## 页面结构

```
document
├── (可能) iframe                       ← 正文可能藏在同源 iframe 里，必须探进去
│   └── article.body-editor-content     ← 正文容器（最稳的选择器）
│       └── [data-block-uuid][data-type=...]   ← 块
└── 侧边栏 / 目录树                      ← 知识库导航（见下节）
```

**探正文的正确姿势**（顺序很重要）：

```js
function findDoc() {
  const frames = document.querySelectorAll('iframe');
  for (const f of frames) {
    try {
      const d = f.contentDocument;              // 跨域会抛异常，try 住
      if (d && d.querySelector('article')) return d;
    } catch (e) {}
  }
  return document;
}
```

选正文容器用**降级链**：`article.body-editor-content` → `article`。

> ⚠️ 不要只查 `document`。钉钉有时把编辑器放进同源 iframe，只查顶层会得到 `no-article`，然后误判"页面抓不到"。

## 块模型的三个关键属性

| 属性 | 含义 | 用法 |
|---|---|---|
| `data-block-uuid` | **块唯一标识** | 跨窗口去重的键 |
| `data-type` | **块类型** | `heading-1`..`heading-6` / `paragraph` / `table` / ... |
| `data-cangjie-key` | **文档内顺序号**（整数） | **恢复真实阅读顺序的键** |

### 最关键的坑：内联 chip 也是 `data-block-uuid`

**不是所有带 `data-block-uuid` 的元素都是真块。**

行内元素（如 @提及、日期 chip、引用卡）也会带 `data-block-uuid`，
但**没有 `data-type`**。

所以：
- **真块** = 带 `data-block-uuid` **且** 带 `data-type`
- **行内 chip** = 带 `data-block-uuid` 但 **无** `data-type` → 应当**向下遍历**，把它里面的文字当普通文本取出来

判定顶层块的正确写法（祖先里不含别的真块）：

```js
const isRealBlock = el => el && el.getAttribute && el.getAttribute('data-type');
const tops = Array.from(art.querySelectorAll('[data-block-uuid]')).filter(b => {
  let p = b.parentElement;
  while (p && p !== art) {
    if (isRealBlock(p)) return false;   // 有真块祖先 → 不是顶层
    p = p.parentElement;
  }
  return true;
});
```

`TreeWalker` 里也必须区分：遇到 `data-block-uuid` 但**无** `data-type` 的节点要**继续往下走**，
只有"真块"才 `FILTER_REJECT` 掉。

### 顺序键：不能靠"窗口顺序 + 窗口内顺序"

分窗采集时，同一块会在相邻窗口重复出现，且窗口内顺序 ≠ 文档顺序。

**必须按 `data-cangjie-key` 升序重排**，否则会出现段落错位、表格跑到别处。

```powershell
$blocks = @($blockMap.Values | Sort-Object { if ($_.k -ge 0) { [int]$_.k } else { [int]::MaxValue } })
```

## 各块类型的抽取要点

### 标题
`data-type="heading-1"` ~ `heading-6"` → 直接映射 `#`~`######`。

### 列表（最容易漏）

列表**不是**块自身带标记，而是**块的祖先容器**带标记：

| 选择器 | 作用 |
|---|---|
| `[data-testid="group-list-container"]` | 列表容器（从块的父级往上 `closest()` 找） |
| `span[data-testid="list-symbol"]` | 列表符号（`●` / `◦` / `1.` ...） |
| 容器的 `style.paddingLeft` | 缩进层级（px 值） |

判定逻辑：

```js
const pp = b.parentElement;
const lc = pp && pp.closest ? pp.closest('[data-testid="group-list-container"]') : null;
let li = null, ind = 0;
if (lc) {
  const sym = lc.querySelector('span[data-testid="list-symbol"]');
  li = sym ? sym.textContent : '?';
  ind = parseInt(lc.style.paddingLeft) || 0;
}
```

渲染时符号 → Markdown 前缀：
- `●`(U+25CF) / `•`(U+2022) / `◦`(U+25E6) → `- `（无序）
- `1.` / `2)` 形式 → `1. `（有序，剥掉尾部的 `.` 或 `)`）
- 其它 → 兜底 `- `

### 表格（含合并单元格）

表格嵌在块内：`b.querySelector('table')`，遍历 `table.rows` → `tr.cells` → `td`。

**单元格取值必须只取该 `td` 内的顶层块**，否则嵌套块的文字会被重复计入：

```js
function cellRuns(td) {
  const inner = Array.from(td.querySelectorAll('[data-block-uuid]')).filter(b => {
    let p = b.parentElement;
    while (p && p !== td) {
      if (isRealBlock(p)) return false;
      p = p.parentElement;
    }
    return true;
  });
  if (inner.length) return inner.map(b => runsOf(b));
  return [runsOf(td)];
}
```

合并单元格：记录 `td.colSpan` / `td.rowSpan`。渲染成 Markdown 表时**摊平**——
Markdown 不支持合并单元格，但要保证**内容一个字不丢**（宁可同一内容出现在多个格子里，
也不能丢行丢列）。

单元格内多段 → 用 `<br>` 连接。

### 代码块

```js
const cb = b.querySelector('[data-language]');
const lang = cb.getAttribute('data-language');           // 语言标注
const lineEls = cb.querySelectorAll('[class*="line"], .cm-line');
const lines = lineEls.length ? [...lineEls].map(l => l.innerText) : [cb.innerText];
```

**必须剥离行号**：编辑器常把行号渲染成独立的纯数字行，渲染时循环剥掉开头的 `^\s*\d+\s*$` 行。

### 行内样式：加粗常常不在 `<strong>` 里

钉钉的加粗**大量使用 inline style**，不是 `<strong>`：

```js
const fw = p.style.fontWeight;
if (fw === 'bold' || fw === 'bolder' || (parseInt(fw) >= 600 && parseInt(fw) <= 900)) bold = true;
```

同类：`fontStyle: italic` → 斜体；`textDecorationLine` 含 `line-through` → 删除线。

**扫描父链**（从文本节点一路向上到块根），而不是只看直接父节点——样式可能挂在中间层 `span` 上。

### void 块（分割线 / 图片）

```js
if (b.getAttribute('data-cangjie-void') === 'true') {
  const inner = b.querySelector('[data-type]');    // 真实类型在里面
  const voidType = inner ? inner.getAttribute('data-type') : 'unknown';   // 'hr' / 'image'
  const img = b.querySelector('img');
  if (img) imgSrc = img.getAttribute('src');
}
```

### Mermaid 图

钉钉把 Mermaid **渲染成 SVG**，然后以 `data:image/svg+xml;utf8,...` 形式塞进 `<img src>`。

- 拓存下来的 `![](data:image/svg+xml;utf8,...)` 是**渲染结果**，不是源码
- 若要 **Mermaid 源码**：页面上定位该图块（用 `data-cangjie-key` 定位），
  从块的 DOM 里找源码文本节点；或从文档的协同数据接口取
- 至少要在交付说明里标注"此处为 Mermaid 渲染图，源码未取回"

## 滚动容器

懒加载长文档必须找准滚动容器。钉钉的容器**没有稳定的 class / id**，
用**几何特征**识别最稳：

```js
let sc = null;
for (const d of doc.querySelectorAll('div')) {
  if (d.scrollHeight - d.clientHeight > 500 && d.clientHeight > 300) {
    if (!sc || d.scrollHeight > sc.scrollHeight) sc = d;   // 取最高的那个
  }
}
```

滚动后必须**手动派发 scroll 事件**（`sc.dispatchEvent(new Event('scroll'))`），
否则虚拟滚动不会触发重新渲染。

## 知识库目录树导航

知识库文档常藏在目录树里，需要先展开/进入，或需要逐篇采集。

| 选择器 | 作用 |
|---|---|
| `[data-rbd-draggable-id="<nodeId>"]` | 目录树的一行（值是 node id） |
| `[data-testid="expand-click-area"]` | 展开箭头 |
| `[data-testid="global-dropdown-trigger"]` | 该行的操作菜单 |

**展开子节点**：

```js
const area = row.querySelector('[data-testid="expand-click-area"]');
const r = area.getBoundingClientRect();
const cx = Math.round(r.left + r.width/2), cy = Math.round(r.top + r.height/2);
area.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, clientX: cx, clientY: cy }));
area.dispatchEvent(new MouseEvent('mouseup',   { bubbles: true, clientX: cx, clientY: cy }));
area.dispatchEvent(new MouseEvent('click',     { bubbles: true, clientX: cx, clientY: cy }));
```

**打开文档（双击行）**：合成事件在这里**经常无效**，必须用 CDP 真实鼠标事件：

```powershell
powershell -File scripts/cdp.ps1 -Port 9333 `
  -DoubleClickSelector "[data-rbd-draggable-id='<nodeId>']" -UrlMatch "alidocs"
```

或用 `harvest.ps1 -Url "https://alidocs.dingtalk.com/i/nodes/<NODE>"` 直接开——
**已知 node id 时这比点目录树可靠得多**，优先走这条路。

## 节点 URL 形态

```
https://alidocs.dingtalk.com/i/nodes/<NODE_ID>
```

`NODE_ID` 是 32 位左右的 base62 串（如 `mweZ92PV6M5zpX0NsqZqgzMBWxEKBD6p`）。
同一个知识库内的文档 node id 往往只有中后段几位不同。
