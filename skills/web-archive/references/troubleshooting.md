# 故障排查对照表

按"现象 → 原因 → 处置"组织。遇到问题先在这里找，别乱试。

---

## 环境 / 连接

| 现象 | 原因 | 处置 |
|---|---|---|
| `Test-CdpPort` 一直 false | 浏览器没用调试端口启动；或端口被别的进程占了 | 关掉已有 Chrome 实例后重跑 `launch-browser.ps1`；换端口 `-Port 9222` |
| `/json` 请求被拒 | 端口不对 / 浏览器已退出 | 重跑 `launch-browser.ps1`；`Get-Process chrome` 确认进程在 |
| 连上但 `SELECTOR-NOT-FOUND` | 连到了错误的标签页 | 用 `-UrlMatch "<url关键字>"` 指定标签页 |
| `NO-TAB` | 没有 `type=page` 的 target | 先 `PUT /json/new?<url>` 开一个；确认不是只连到 iframe target |

---

## 登录态

| 现象 | 原因 | 处置 |
|---|---|---|
| 页面跳到登录页 | profile 里登录态失效 | 请用户在弹出的浏览器里**手动登录一次**，之后复用。**不索取密码** |
| 正文一直 `articleFound: false` 但页面看着正常 | 登录墙后是空壳页 | 同上；检查 URL 是否含 `login` / `passport` / `sso` |
| 明确为登录墙却被当成正文 | 选择器命中 `body` 或空壳 | `harvest.ps1` 会检测 URL 与密码框并返回 `login-required`；不要用 `body` 强行继续 |
| 换了 profile 目录后要重新登录 | profile 换新了 | 保持 `-ProfileDir` 稳定；默认 `%LOCALAPPDATA%\web-archive-profile` |
| 用户日常浏览器已被打开，调试端口起不来 | Chrome 复用已存在的实例，忽略新参数 | 完全退出 Chrome 再启动调试实例（或用独立 profile 启动，互不干扰） |

---

## 抽取为空 / 内容偏少

**先按这个顺序排查，不要跳步：**

| 顺序 | 假设 | 验证 | 处置 |
|---|---|---|---|
| 1 | 正文在 **iframe** 内 | 探针看 `inFrame` / `iframeCount` | 抽取 JS 里加 `findDoc()`；跨域则连 iframe 的独立 target |
| 2 | 内容**尚未渲染** | 探针看 `topLevelBlocks` 是否为 0 | 加重轮询等待；等就绪后再多等 2~2.5s |
| 3 | **选择器不对** | 探针看 `articleSelector` / `typeStats` | 用探针输出的 `samples` 校正选择器，覆盖 `-ArticleSelector` |
| 4 | 需要**登录** | 看 URL 是否跳登录页 | 请用户登录 |
| 5 | 内容在 **canvas** 里 | 探针 `totalMatchedBlocks = 0` 且页面有 canvas | 改用站点自带导出 / 截图 OCR，并标注降级 |

> **反模式**：抽取为空就直接下结论"这页面抓不了"。99% 是上面 1~3 之一。

---

## 内容缺失 / 错位

| 现象 | 原因 | 处置 |
|---|---|---|
| 段落**错位**、顺序乱 | 用了"窗口顺序 + 窗口内顺序" | 必须按顺序键（钉钉 = `data-cangjie-key`）重排 |
| 飞书块完全抓不到 | 仍使用钉钉的 `data-block-uuid` / `data-type` | 用 `-Adapter feishu`，或探针后覆盖 `-BlockIdAttr` / `-BlockTypeAttr` |
| 普通 HTML 抓不到块 | 页面没有块属性 | 用 `-Adapter generic`，按语义标签生成稳定 DOM 路径 ID |
| 中间**整段缺失** | 滚动步长 ≥ 一屏高度，两块之间从未进视口 | 调小 `-StepRatioPct`（如 1）；步长必须 < 视口高 |
| 末尾内容缺失 | 最后一屏懒加载未触发 | 循环后再滚到底（`scrollTop=99999999`）抓一次 |
| 同一段**重复**出现 | 去重键有问题 | 确认以 `data-block-uuid` 去重；检查是否把行内 chip 也当了独立块 |
| 列表**层级丢失** | 没读 `group-list-container` 的 `paddingLeft` | 按缩进值换算空格/前缀 |
| 列表**符号丢失** | 没读 `list-symbol` | 取 `span[data-testid="list-symbol"]` 的 `textContent` |
| 加粗**全丢** | 只找了 `<strong>` | 钉钉加粗在 inline `style.fontWeight`（600~900），要扫父链 |
| 表格**行列错乱** | 只取一层 `td` 文本 | 用 `cellRuns()` 只取 `td` 内顶层块 |
| 单元格内容**重复** | 把嵌套块文字算了两次 | 同上 |
| 代码块带**行号** | 行号被当正文行 | 渲染时剥掉开头 `^\s*\d+\s*$` 的行 |
| 表格里的 `\|` 把表**撑破** | 没转义 | 单元格与行内内容都要 `-replace '\|','\|'` |
| 合并单元格错位 | `rowSpan/colSpan` 未展开 | 渲染阶段按网格覆盖并复制内容 |
| 行内代码**反引号冲突** | 内部反引号未转义 | 先把 `` ` `` 双写再外包一层反引号 |

---

## 脚本运行

| 现象 | 原因 | 处置 |
|---|---|---|
| `&&` / 三元 / `??` 报语法错 | PowerShell 5.1 不支持 PS7 语法 | 改 `;` / `if-else` / 显式判 `$null` |
| 中文输出乱码 | `.ps1` 存成 ANSI 或写文件没指定编码 | 脚本存 UTF-8 **with BOM**；读写用 `[System.Text.Encoding]::UTF8` |
| `ConvertFrom-Json` 报错 | payload 内含非法 JSON（未转义换行/引号） | 用 `ConvertTo-Json` 生成，不要手拼字符串 |
| JSON 嵌套字段变字符串 | `ConvertTo-Json` 默认 `-Depth 2` | 显式给 `-Depth`（参数 6~8，大对象 12~14） |
| 求值返回 `EVAL-NULL-OR-ERROR` | 表达式抛异常 / 超时 / 异步没 await | 看 `exceptionDetails`；Promise 必须 `awaitPromise: true` |
| 大 payload 截断 | 接收缓冲区太小 | 缓冲区提到 16~32MB，并循环读到 `EndOfMessage` |
| 求值卡死 | 死等响应，事件帧淹没了结果 | 严格按 `id` 匹配响应，加 deadline 兜底 |
| 脚本执行策略拦截 | ExecutionPolicy | 用 `powershell -NoProfile -ExecutionPolicy Bypass -File` |

---

## 交互失效

| 现象 | 原因 | 处置 |
|---|---|---|
| 合成点击**没反应** | 框架只信 `isTrusted === true` 的事件 | 改用 CDP `Input.dispatchMouseEvent` 派发真实鼠标事件 |
| 真实鼠标点击也无效 | 坐标不对（元素在视口外 / 取的是 offset 不是视口坐标） | 先 `el.scrollIntoView()`；用 `getBoundingClientRect()` 取视口坐标 |
| 双击没打开文档 | 缺 `mousePressed` 的 `buttons: 1` | 按住状态要显式给 `buttons: 1` |
| 展开子节点没反应 | `expand-click-area` 需要 mousedown+mouseup+click 三件套 | 三个事件都派发；坐标取该元素的 rect 中心 |
| 滚动后内容没更新 | 虚拟滚动没收到 scroll 事件 | 改 `scrollTop` 后手动 `dispatchEvent(new Event('scroll'))` |

> **优先用 URL 直开，而不是点目录树**：已知 node id 时，
> `harvest.ps1 -Url ".../nodes/<NODE>"` 比模拟点击可靠得多。

---

## 渲染输出

| 现象 | 原因 | 处置 |
|---|---|---|
| 图片是 `data:image/svg+xml...` | Mermaid / 图表只暴露渲染图 | 优先读 `data-mermaid-src` / `data-mermaid` / `.mermaid` / `code.language-mermaid`；源码确实不存在才标注降级 |
| 未知代码语言变成空围栏 | 用了白名单过滤 | 保留任意安全语言标识，未知语言也要输出 |
| 图片 src 是 1px 占位图 | 懒加载图片，真地址在 `data-*` | 读 `data-src` / `data-original` / `data-lazy-src` |
| 空白行过多 / 过少 | 块间空行处理不一致 | 渲染末尾统一折叠连续空行（保留 1 个） |
| 文档没有来源信息 | 忘了写头部 | 头部固定三行：标题 / 来源 URL / 提取时间 |

---

## 交付前自检清单

- [ ] 文档头部有 **标题 + 来源 URL + 提取时间**
- [ ] 抽样比对过 **首段 / 中段 / 末段**
- [ ] 表格**行列数**与页面一致
- [ ] 代码块**语言标注**保留、行号已剥离
- [ ] 有**采集统计**（窗口数 / 块数 / 表格 / 图片 / 代码块）
- [ ] 任何**漏采或降级**都已显式说明
- [ ] 只采集了用户有权访问的内容（红线复核）
