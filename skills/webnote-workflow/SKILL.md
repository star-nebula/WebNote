---
name: webnote-workflow
description: 把网页/本地内容整理成"可信本地笔记"或按原结构无损拓存。当用户给出网页 URL、云文档、浏览器剪藏、本地 PDF/DOCX/图片/视频/音频/小红书链接，要求"无损保存/网页归档/整理成笔记/提炼要点"时使用。知识化流程含多 Agent 版与单对话框分段版；防复制页、钉钉/飞书云文档和懒加载长文走 web-archive 分支。
agent_created: true
---

# WebNote · 总编排

把"内容采集 → 整理分类 → 提炼笔记 → 确认发布"组织为**调度器（主会话） + 三个独立执行角色**。

项目目标是**可信**：正文不凭空编、核查必须独立、落地必待确认。

## 第一步：定位项目根（必做，不要跳）

本 skill 依赖项目内的 `tools/`、角色定义与步骤卡。**先定位项目根**，判定标准是目录下同时存在 `docs/architecture.md` 和 `tools/`：

1. **当前工作区就是项目根** → 直接用
2. **不是** → **停下来问用户项目根目录在哪**，拿到路径后再继续

**不要靠"我的上一级目录是谁"去推断。** 那样在 skill 被装到用户级目录（如 `~/.workbuddy/skills/`）时会推断出一个错误的项目根，然后一路静默降级——工具找不到，流程却还在跑，产出的是一堆没有依据的笔记。这是本 skill 最容易出事的地方。

## 资源索引

路径说明：**全部资源都相对于项目根**（见上方第一步的定位逻辑）。角色定义、步骤卡与工具是**流程资产**，归项目根，不属于本 skill 的私有实现。

| 资源 | 位置（相对项目根） | 何时加载 |
|---|---|---|
| 流程总览与理念 | `docs/architecture.md` | 首次使用时读一次 |
| **采编主卡** | `<项目根>/skills/webnote-workflow/references/steps/collect.md` | 第 1 步，必读 |
| 采编 · 图片分支 | `<项目根>/skills/webnote-workflow/references/steps/collect-image.md` | 判断为图片时 |
| 采编 · 视频音频分支 | `<项目根>/skills/webnote-workflow/references/steps/collect-video-audio.md` | 判断为视频/音频时 |
| 采编 · 小红书 | `skills/xhs-note/SKILL.md` | 判断为小红书时 |
| **采编 · 无损拓存** | `skills/web-archive/SKILL.md` | 防复制页、云文档、登录态长文、要求完整保存/归档时 |
| 无损拓存模式卡 | `<项目根>/skills/webnote-workflow/references/steps/collect-web-archive.md` | 进入 web-archive 分支前 |
| **归类师定义** | `<项目根>/agents/classifier.md` | 第 2 步派发时 |
| **笔记匠定义** | `<项目根>/agents/distiller.md` | 第 3 步派发时 |
| **核查官定义** | `<项目根>/agents/verifier.md` | 第 4 步派发时 |
| 确认步骤卡 | `<项目根>/skills/webnote-workflow/references/steps/confirm.md` | 第 5 步 |
| 模式 B 三段式提示词 | `<项目根>/skills/webnote-workflow/references/degraded-single-dialog.md` | 无 subagent 能力时 |
| 采编工具 | `tools/*.py` | 见采编卡的路由表 |

**规则**：角色定义与步骤卡是**唯一事实来源**。派发 subagent 时把对应文件交给它，**不要凭记忆复述角色要求**——复述必然走样，最容易漏掉的是铁律。

## 触发与内容确认

用户给出内容（URL / 本地路径 / 已存正文）并要整理成笔记时触发。先做**内容清单确认**：逐个判断媒体格式（图文/图片/视频/音频/文档/小红书/无法判断），拿不准就问用户，不擅自猜测。

## 先选输出模式

1. **无损存档模式**：用户说“保存、归档、拓存、完整抓取、不能复制、钉钉/飞书云文档、结构不要变”时，加载 `skills/web-archive/SKILL.md` 与 `skills/webnote-workflow/references/steps/collect-web-archive.md`。输出结构化原文到 `Resources`，不摘要、不润色、不进入归类/笔记匠。
2. **知识提炼模式**：用户说“整理成笔记、提炼、总结成知识”时，继续本文件后续的采编 → 归类 → 笔记 → 核查流程，输出 `Knowledge`。
3. **两种都要**：先用无损存档模式落 `Resources`，核对来源完整后再进入知识提炼；知识笔记通过 frontmatter 回指已保存的来源，不复制第二份原文。

## 前置检查

1. 确认 `tools/` 下工具存在
2. 内容涉及**图片语义 / 视频画面**且需要理解时：检查环境变量 `DEEPSEEK_API_KEY`，未设置则提示用户配置，不擅自跳过、不编造 Key
3. 小红书需 Cookie（见 xhs-note skill）；浏览器页面读取走 BrowserSkill

## 执行模式

### 模式 A · 多 Agent（工具支持 subagent 时，推荐）

调度器自做**采编**与**确认**；其余三步用独立 subagent：

| 步 | 执行者 | 加载 | 上下文要求 | 产出 |
|---|---|---|---|---|
| 1 采编 | 调度器 | `<项目根>/skills/webnote-workflow/references/steps/collect.md`，按媒体路由只加载命中的分支卡 | — | `00-采编清单.md` |
| 2 归类师 | subagent | `<项目根>/agents/classifier.md` | `isolated` 独立上下文 | `01-整理清单.md` |
| 3 笔记匠 | subagent | `<项目根>/agents/distiller.md` | `isolated` 独立上下文 | `02-笔记.md` |
| 4 核查官 | subagent | `<项目根>/agents/verifier.md` | **`fresh` 全新，与笔记匠零共享** | `03-核查表.md` |
| 5 确认 | 调度器 | `<项目根>/skills/webnote-workflow/references/steps/confirm.md`，转述源与可疑条目单列 | — | `04-待确认提案.md` |

### 模式 B · 单对话框分段（无 subagent 能力时降级）

同一对话内完成采编 / 归类 / 提炼 → **在核查前停下**，提示用户把 `00/01/02` 产物与原文带到**新对话**，让新对话读 `<项目根>/agents/verifier.md` 执行核查 → 核查表带回后读 `<项目根>/skills/webnote-workflow/references/steps/confirm.md` 做确认。

三段的具体提示词（用户直接复制粘贴）见 `<项目根>/skills/webnote-workflow/references/degraded-single-dialog.md`。

**核查那道必须另开新对话。** 别在笔记匠那个对话里接着问。

若确实无法开新对话，按 `<项目根>/agents/verifier.md` 的「降级声明」要求**显式标注**，不要用一份看起来合规的表掩盖独立性不足。

## 三条不可逾越

1. **正文不凭空编** —— 文本来自工具提取或用户已有，没有就如实写"无"
2. **核查独立** —— 核查者不能是笔记的撰写者（`context: fresh`）
3. **落地必待确认** —— 所有删除/归档/发布/写入长期记录的动作停在"待确认"，用户逐条点头才执行

## 产出

- 输出目录：每次运行在 `runs/` 下建 `YYYY-MM-DD-主题/`，五个文件并列写入
- **起手**：把 `runs/_template/` 整个复制成 `runs/<日期-主题>/`，只填内容不改表头（表头与步骤卡一致，测试会校验）
- 原文**只读**，不复制、不移动，清单只记录来源路径
- **收尾**：把 `04-待确认提案.md` 展示给用户，等逐条确认后执行落地动作
