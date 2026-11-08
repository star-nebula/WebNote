# 站点适配手册

不同站点的正文容器与块模型差异很大。**策略是统一的，选择器是站点特定的**——
所以流程固定为「先探针 → 再开采」。

## 通用适配流程

```
1. launch-browser.ps1          起调试浏览器（持久化 profile，登录态一次搞定）
2. cdp.ps1 -JsFile probe-dom.js 探针：正文在哪？块模型是什么？要滚动吗？
3. 依据探针输出决定：
   - 有 [data-block-uuid] 块模型 → 直接 harvest（改 ArticleSelector / OrderAttr）
   - 无块模型（普通 HTML）      → 写站点专用抽取 JS（见下方「无块模型站点」）
4. harvest → merge-blocks → render-md → 校验
```

探针输出里最该看三行：`articleSelector`、`topLevelBlocks`、`needsWindowedHarvest`。

---

## 场景 1：防复制新闻页 / 博客

**症状**：右键被禁、文字选不中、Ctrl+C 无效、`user-select: none`、`oncopy` 被 return false。

**为什么本方案天然免疫**：我们不调用复制功能，直接读 DOM。所以：
- `user-select: none` → 无关，DOM 文本还在
- `oncopy="return false"` → 无关，不触发 copy 事件
- 禁用右键 → 无关，不用右键
- 剪贴板拦截 → 无关，不读剪贴板

**做法**：
1. 探针找正文容器。新闻站常见 `article`、`main`、`.article-content`、`#content`
2. 用 **Readability 式策略**兜底：在候选容器里按"文本密度"打分，选得分最高的
3. 沿 DOM 树收集文本时，**过滤噪音节点**：`nav` / `aside` / `footer` / `.ad` / `.share` / `script` / `style`
4. 图片：`img[src]`，注意 `data-src` / `data-original` 这类**懒加载占位属性**——
   真实地址常在 `data-*` 里，`src` 是 1px 占位图

**懒加载图片处理**：

```js
const real = img.getAttribute('data-src')
          || img.getAttribute('data-original')
          || img.getAttribute('data-lazy-src')
          || img.getAttribute('src');
```

### 兜底：无块模型的普通 HTML 站点

这类站点没有 `data-block-uuid`，需要遍历 HTML 标签树自建块结构：

```js
const BLOCK_TAGS = new Set(['P','H1','H2','H3','H4','H5','H6','LI','BLOCKQUOTE','PRE','TABLE','HR','FIGURE','FIGCAPTION','UL','OL']);
// 遍历正文容器，遇到 BLOCK_TAGS 就生成一个块；行内样式走 runsOf 同样的逻辑
```

---

## 场景 2：钉钉云文档（alidocs）

**最成熟的一条路**，DOM 块模型完整、可 100% 结构化还原。
详见 `dingtalk-doc-model.md`。要点回顾：

- 正文在 `article.body-editor-content`（**可能在 iframe 内**）
- 块 = `[data-block-uuid][data-type]`，顺序 = `data-cangjie-key`
- 列表靠祖先 `[data-testid="group-list-container"]` + `list-symbol`
- 加粗常是 inline `fontWeight`，不是 `<strong>`
- 直接跑 `harvest.ps1 -Url "https://alidocs.dingtalk.com/i/nodes/<NODE>"`

---

## 场景 3：飞书云文档（Feishu Docs）

`https://xxx.feishu.cn/docx/<DOC_TOKEN>` / `/wiki/<TOKEN>`

**与钉钉的关键差异**：飞书也是 canvas/block 渲染，但**块属性名不同**。
必须**先探针**，不要套用钉钉的选择器。

看探针输出的 `dataAttrsSeen` —— 飞书常见的块标记形如：
- `data-block-id`（而非 `data-block-uuid`）
- `data-block-type`（而非 `data-type`）
- 顺序可能需要靠 `data-record-id` 或 DOM 顺序

**适配方式**：探明后覆盖参数：

```powershell
powershell -File harvest.ps1 -Url "https://xxx.feishu.cn/docx/XXX" -Prefix fs1 `
  -Adapter feishu
```

默认飞书适配器使用 `data-block-id` + `data-block-type`，正文容器优先 `.docx-page-block / main / [role=main] / article`。若实测属性不同，再用 `-BlockIdAttr`、`-BlockTypeAttr`、`-ArticleSelector` 覆盖。没有可靠顺序键时按“窗口 + 窗内 DOM 位置”保序。

普通 HTML 防复制页使用：

```powershell
powershell -File harvest.ps1 -Url "https://example.com/a" -Prefix html1 -Adapter generic
```

> 若飞书探针显示 `hasBlockModel = false`，说明它把内容画在 `<canvas>` 里
> （纯 canvas 文档无法从 DOM 取文本）。此时改用：
> 1. 页面自带的导出功能（有权限时应优先用）2. 或截图 + OCR 兜底
> 并在交付说明中明确标注降级。

---

## 场景 4：登录态 / 鉴权页面

**做法**：持久化 profile。

```powershell
# 第一次：起浏览器，请用户手动登录一次
powershell -File launch-browser.ps1 -Port 9333

# 之后所有会话：直接复用，无需再登录
```

**红线**：
- ❌ 不向用户索取账号密码
- ❌ 不注入 Cookie、不伪造 token、不绕过权限校验
- ❌ 不绕过付费墙 / 验证码 / 访问控制
- ✅ 只复用用户**本机已有**的登录态
- ✅ 遇到权限不足 → 说明情况并停止

**登录态检测**：探针若返回 `articleFound: false` 且页面 URL 跳到登录页
（含 `login` / `passport` / `sso`），说明登录态失效 → 请用户重新登录。

---

## 场景 5：长文档 / 虚拟滚动

**症状**：一次性 `innerText` 只能拿到当前视口；滚回去发现上面的内容"没了"（被卸载）。

**唯一正解：分窗采集 + 按块去重**（`harvest.ps1` 已内置）。

参数调优经验：

| 情况 | 调整 |
|---|---|
| 有块漏采 | 调小 `-StepRatioPct`（如 1），或调大 `-WaitMs` |
| 太慢 | 调大 `-StepRatioPct`（如 3），但要复查是否漏块 |
| 懒加载很慢 | `-WaitMs 2500` |
| 无限滚动（如动态 feed） | 设 `-MaxWindows` 并明确告知用户"只采了前 N 屏" |
| 短页面 | `-SingleView`，不滚动 |

**步长原理**：`max(300px, 容器高 × 2%)`。
步长必须**小于一个视口高度**，否则两窗之间的内容永远没进过视口 → 漏采。

**尾部兜底**：循环结束后再滚一次到底（`scrollTop = 99999999`）抓一次，
防止最后一屏的懒加载内容漏掉。

---

## 场景 6：内容在 iframe 内

**症状**：探针报 `inFrame: true`，或 `articleFound: false` 但肉眼看得到内容。

**做法**：所有抽取 JS 的第一步都必须是 `findDoc()`（见 `cdp-recipes.md`）。
只要 iframe **同源**就能读 `contentDocument`；**跨域**读不到（会抛异常）。

跨域 iframe 的出路：
1. 用 `/json` 列出全部 target —— **iframe 本身可能是独立 target**，
   直接连它的 `webSocketDebuggerUrl`，`document` 就是那个 iframe 的文档
2. 或用 `Page.getFrameTree` 拿 frame id，再对 frame 执行求值

> `/json` 返回里 `type` 为 `iframe` 的条目就是这个用途。这是跨域 iframe 的正规解法。

---

## 场景 7：深度防爬对抗

**能做的**：
- 用真实浏览器 + 真实用户输入事件（`Input.dispatchMouseEvent`）
- 复用真实登录态（profile）
- 放慢节奏（单窗 ≥ 1s）、不并发
- 真实鼠标轨迹（滚轮用 `Input.dispatchMouseEvent` 的 `mouseWheel` 而非 JS 改 `scrollTop`）

**不该做的**：
- 不破解验证码
- 不伪造成本极高的指纹对抗
- 不绕过访问控制 —— 这是红线，不是技术问题

**判断标准**：只要目标内容**用户自己有权在浏览器里看到**，拓存就是正当的
（用户本来就能复制，只是站点不让复制）。一旦需要"获得本不该有的权限"，立即停止。
