---
name: web-archive
description: "Faithfully extract and preserve web content that resists copying — anti-copy / no-select pages, DingTalk cloud docs (alidocs), Feishu cloud docs, login-gated and lazily-rendered long pages — and render it into a structured, lossless local document. Use when the user gives a URL and wants its content saved, archived, mirrored, exported, or extracted, or when a page cannot be copied, selected, right-clicked, or exported."
agent_created: true
---

# Web Archive — 网页内容拓存

把"复制不了"的网页落成本地文档。核心思路：**不依赖页面的复制功能**，而是接管真实浏览器、读取渲染后的 DOM 块结构、重建为 Markdown。

## 何时用本 Skill

| 场景 | 说明 |
|---|---|
| 防复制页 | 禁用右键 / 禁用选中 / `user-select:none` / 剪贴板拦截 |
| 云文档 | 钉钉云文档（`alidocs.dingtalk.com`）、飞书云文档（`feishu.cn/docx/...`） |
| 长文档 | 懒加载 / 虚拟滚动，滚出视口即卸载 |
| 登录态页 | 需要账号登录才可见 |
| 结构复杂页 | 多级标题、表格合并单元格、代码块、Mermaid 图 |

**不适用**：纯静态且可直接复制的普通网页（直接抓 HTML 更快）、需要破解付费墙或权限的内容（见下方红线）。

## 红线（先读这一段）

1. **只复用用户本机已有的登录态**，只采集用户有权访问的内容。
2. **禁止**绕过付费墙、账号权限、验证码、任何访问控制。权限不足 → 说明情况并停止。
3. **禁止**向用户索取账号密码。需要登录时，请用户在弹出的浏览器窗口中自行完成。
4. **不做内容改写**：任何润色、纠错、摘要都是越界。拓存 = 复刻。
5. **采集礼貌**：单窗等待 ≥ 1s，不并发轰炸；只采集明确指定的页面。

## 技术底座：CDP

所有采集通过 **Chrome DevTools Protocol** 完成，无需任何浏览器插件：

- 浏览器以 `--remote-debugging-port=9333 --user-data-dir=<专用profile>` 启动 → 登录态持久化在 profile 里
- `GET http://127.0.0.1:9333/json` → 列出标签页
- `PUT http://127.0.0.1:9333/json/new?<url-encoded-url>` → 开新标签页
- `GET http://127.0.0.1:9333/json/close/<id>` → 关标签页
- WebSocket 连到标签页的 `webSocketDebuggerUrl` → 发 `Runtime.evaluate` / `Input.dispatchMouseEvent`

细节与 PowerShell 实现配方见 `references/cdp-recipes.md`。

## 标准工作流

### Step 0 · 判定页面类型
问清三件事：**URL**、**输出格式**（默认 Markdown）、**保存路径**（默认当前工作目录）。
然后判定类型，决定走哪条路：

| 类型 | 走法 |
|---|---|
| 钉钉云文档 / 长文档 | `-Adapter dingtalk`，全流水线（Step 1 → 5） |
| 飞书云文档 | 先探针，使用 `-Adapter feishu`，再跑全流水线 |
| 普通防复制 HTML | 使用 `-Adapter generic`，按语义标签生成稳定块 ID |
| 短的单视图页 | 跳过分窗，直接单次抽取 + 渲染 |
| 未知新站点 | **先跑探针**（Step 1.5），确认块模型后再开采 |

### Step 1 · 起环境
```powershell
# 1) 启动调试模式浏览器（若尚未运行）
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/launch-browser.ps1 -Port 9333

# 2) 确认端口与标签页
Invoke-RestMethod -Uri "http://127.0.0.1:9333/json" -Method Get |
  Where-Object { $_.type -eq 'page' } | Select-Object id, url
```

### Step 1.5 · （新站点必做）DOM 探针
```powershell
# 把 probe-dom.js 喂给 CDP 求值，打印块类型统计 + 结构样本
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/cdp.ps1 `
  -JsFile scripts/probe-dom.js
```
输出会告诉你：总块数、各 `data-type` 分布、标题/列表/引用/代码/表格/图片的 HTML 样本。
**确认选择器对得上再往下走。**

### Step 2 · 采集
```powershell
# 长文档：分窗滚动采集
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/harvest.ps1 `
  -Url "https://alidocs.dingtalk.com/i/nodes/<NODE>" -Prefix "doc1" -Port 9333 -Adapter dingtalk
# 产物：work/<Prefix>_w1.json, _w2.json, ...（每窗一个，含全部顶层块）

# 飞书
powershell -File scripts/harvest.ps1 `
  -Url "https://xxx.feishu.cn/docx/<TOKEN>" -Prefix fs1 -Adapter feishu

# 普通 HTML 防复制页
powershell -File scripts/harvest.ps1 `
  -Url "https://example.com/article" -Prefix html1 -Adapter generic
```

### Step 3 · 合并去重
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/merge-blocks.ps1 `
  -Dir work -Prefix "doc1"
# 产物：work/merged.json（按块唯一键去重 + 按阅读顺序重排），并打印标题大纲
```

### Step 4 · 渲染文档
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/render-md.ps1 `
  -MergedPath work/merged.json -Title "文档标题" -Source "https://..." -OutPath out/doc1.md
```

### Step 5 · 校验与交付
- 抽样比对：**首段 / 中段 / 末段**各一处；核对表格行列数、代码块数量
- 报告统计：窗口数、块数、表格数、图片数、代码块数
- 交付时写明保存路径；**有任何漏采或降级必须显式说明**
- 自动化回归：`powershell -File _agent_scripts/test-web-archive.ps1`

## 输出契约

文档头部固定三行：

```markdown
# {标题}
> 来源: {URL}
> 提取时间: {YYYY-MM-DDTHH:mm:ss.sssZ}
```

然后按块渲染：`heading-N`→`#`~`######`、列表→`-`/`1.`、引用→`>`、表格→Markdown 表、代码块→围栏（带语言）、图片→`![]()`、分割线→`---`。

**顺序必须是阅读顺序，不是采集顺序。**

- 合并单元格按 `rowSpan/colSpan` 展开并复制内容。
- 未知代码语言保留原语言标识；空语言才输出无标注围栏。
- Mermaid 优先读取 `data-mermaid-src`、`data-mermaid`、`.mermaid` 或 `code.language-mermaid` 源码；只有渲染图时明确降级。
- `auto` 按 URL 选择 `dingtalk` / `feishu` / `generic`；未知站点仍应先探针。
- 连续 `MaxStalledWindows` 个窗口无进展、连续空抽取或登录墙会停止，避免 400 窗空转。

## References

- `references/cdp-recipes.md` — CDP 配方全集 + PowerShell 5.1 踩坑
- `references/dingtalk-doc-model.md` — 钉钉云文档 DOM 块模型、选择器表、抽取 JS
- `references/site-playbook.md` — 站点适配手册（防复制页 / 新闻站 / 飞书 / 目录树导航）
- `references/troubleshooting.md` — 故障排查对照表

## Scripts

| 脚本 | 作用 |
|---|---|
| `scripts/launch-browser.ps1` | 以调试模式 + 持久化 profile 启动浏览器 |
| `scripts/cdp.ps1` | 可复用的 CDP 求值封装（连标签页 + evaluate） |
| `scripts/probe-dom.js` | DOM 探针：块类型统计 + 结构样本 |
| `scripts/harvest.ps1` | 分窗滚动采集（长文档核心） |
| `scripts/merge-blocks.ps1` | 按块唯一键去重合并 + 排阅读顺序 |
| `scripts/render-md.ps1` | 合并结果 → Markdown |

> 通用化说明：`harvest.ps1` 的正文容器选择器与顺序键按站点不同而不同。
> 钉钉云文档用 `article` + `[data-block-uuid]` + `data-cangjie-key`（内置默认即此）。
> 其他站点请先用探针确认，再用 `-ArticleSelector` / `-OrderAttr` 覆盖。

## WebNote 集成模式

本 skill 是 WebNote 的无损存档分支，与知识提炼分支共用“真实来源、不编造、可核验”的底线。

- 只要求保存、镜像或归档时：输出结构化 Markdown 到 `E:\knowledge\Resources\`，到此停止。
- 同时要求知识笔记时：先完成本 skill 的采集与抽样校验，再从已落库来源提炼到 `E:\knowledge\Knowledge\`。
- 无损存档模式禁止摘要、润色和知识重构；知识提炼模式不得替代原始存档。
