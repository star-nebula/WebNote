# WebNote · 网页笔记工作流

> 把"内容采集 → 整理分类 → 提炼笔记 → 确认发布"拆成**调度器（主会话） + 三个独立 Agent** 分工协作。确定性的事调度器（主会话）自己干（画面采集为可选 AI 增强），只有真正需要独立判断的才交给 subagent。

[English](README.en.md) · [中文文档](#目录结构) · [给 AI 的入口 AGENTS.public.md](AGENTS.public.md)

---

## 快速开始

### 先说清楚：你什么都不装也能用

这套工作流的核心价值是**流程设计和角色定义**，不是那些 Python 脚本。脚本只是采编阶段的加速器——没有它，你手动把正文贴给 AI，整条流程照样跑得通。

| 你想处理 | 额外需要什么 |
|---|---|
| 图文内容（正文你自己提供） | **零依赖**，clone 完就能用 |
| PDF / Word 文档 | `pip install pypdf python-docx` |
| 图片上的文字 | `pip install rapidocr-onnxruntime` |
| 视频语音转写 | `pip install faster-whisper` + `ffmpeg` |
| 图片 / 视频画面理解 | 上面几项 + `DEEPSEEK_API_KEY` |
| 防复制页 / 钉钉飞书云文档无损拓存 | Chrome 或 Edge；PowerShell 5.1+ |

不确定自己现在能用什么？跑一下自检（纯标准库，无需先装东西）：

```bash
python tools/check-env.py
```

它会列出当前可用能力、缺什么、怎么补。**缺的能力只影响对应媒体，不会让流程失败**——没有 ffmpeg 就处理不了视频，图文流程照常可用。

### 三条使用路径

**路径 A · 装配 skill（推荐，一次装配长期生效）**

把项目内 `skills/` 目录装进你的 AI 工具，之后**自然对话即触发**——直接说"把这个网页整理成笔记"，AI 自动加载 `webnote-workflow` skill。

- WorkBuddy / Codex：`<项目>/skills/` → `.workbuddy/skills/`、`.codex/skills/`
- Claude Code：`<项目>/skills/` → `.claude/skills/`
- 工具不支持项目级 skill → 走路径 B

**路径 B · 一条提示词（不装配也能用，任何 AI 都行）**

- 有子代理能力的工具（Claude Code / CodeBuddy / Cursor）→ [`prompts/入口提示词-全自动.md`](prompts/入口提示词-全自动.md)
- 纯聊天界面（ChatGPT / Claude 网页版）→ [`prompts/入口提示词-单对话框.md`](prompts/入口提示词-单对话框.md)

复制对应文件里的代码块，把项目路径换成你的实际路径，连同内容一起发给 AI。

**路径 C · 手动流水线**

按五步顺序，每次让 AI 读对应的定义文件（见下方目录结构）。采编和确认你自己串。想先看产出长什么样：[`examples/`](examples/) 有一次完整运行的全部文件。

> 分层说明：`webnote-workflow` 是**总编排 skill**；图片、视频、小红书和网页无损拓存四条链路分别由 `skills/image-extract`、`skills/video-extract`、`skills/xhs-note`、`skills/web-archive` 承载，采编时按内容类型加载。五步细则见 [Webpage note workflow.md](Webpage%20note%20workflow.md)。

---

## 中文文档

### 项目简介

WebNote 是一套**以"可信"为核心的网页内容整理工作流**。它的目标不是帮你更快地生产，而是帮你**更可靠地把网页内容变成自己的知识**。

> 本项目在 [Axton Liu《Agent OS 的第一课：会分工，才会用 Agent》](https://www.axtonliu.ai/newsletters/ai-2/posts/agent-os-workstation-division) 一文的理念启发下自行实现与改进，落地成一套可直接复用、按文件流水线运行的工作流。本仓库仅借鉴其"分工隔离 / 独立核查 / 确认闸门"三层设计思路，所有文档与提示词均为独立撰写。

### 架构

**不是每一步都需要独立的 AI 上下文。** 确定性的事调度器（主会话）自己干（画面采集为可选 AI 增强），只有真正需要独立判断的才交给 subagent：

```
调度器（主会话）
├── 1. 采编（主会话自己做——URL 正则 + CLI 工具提取文本）
│      → 产出 00-采编清单.md
│
├── 2. 归类师（独立 subagent——四选一语义分类）
│      → 产出 01-整理清单.md
│
├── 3. 笔记匠（独立 subagent——提取 3~5 条核心要点）
│      → 产出 02-笔记.md
│
├── 4. 核查官（全新 subagent——逐条比对原文 vs 笔记）
│      → 产出 03-核查表.md
│
└── 5. 确认（主会话自己做——汇总提案，全部停在待确认）
       → 产出 04-待确认提案.md
```

**为什么有些步骤不是独立 Agent：**

| 步骤 | 是否独立 | 理由 |
|------|---------|------|
| 采编 | ❌ 主会话内化 | URL 分类用正则，文本提取调用 CLI 工具——**默认确定性逻辑不需要 AI**（画面采集为可选 AI 增强，见下） |
| 归类师 | ✅ 独立 | 四选一分类需要理解正文语义，归类师的判断不应影响笔记匠 |
| 笔记匠 | ✅ 独立 | 核心创作任务，需要完整上下文专注正文 |
| 核查官 | ✅ **必须独立** | 安全闸门——笔记匠自己核查自己等于自检，查不出自己编了什么 |
| 确认 | ❌ 主会话内化 | 不读原文、不做新判断，只是汇总 + 约束落地行为 |

### 功能说明

| 阶段 | 执行者 | 输入 | 输出 | 关键约束 |
|------|--------|------|------|---------|
| 采编 | 调度器（主会话） | 原始 URL + 已有正文 | `00-采编清单.md` | 规则分类 + CLI 工具，默认不依赖 AI；**画面采集（教程/录屏类视频）为可选 AI 增强** |
| 归类师 | subagent | 采编清单中有正文的内容 | `01-整理清单.md` | 只归类，不提炼 |
| 笔记匠 | subagent | 整理清单中有正文的页面 | `02-笔记.md` | 只依据正文，**标注出处与来源类型** |
| 核查官 | subagent（全新） | 原文 + 笔记 | `03-核查表.md` | **必须独立 Agent**，三态判定 |
| 确认 | 调度器（主会话） | 前四道产出 | `04-待确认提案.md` | 全部停在"待确认" |

四选一分类：

- **学习**：有能直接上手的技术、方法或知识
- **借鉴**：写法、结构、表达方式值得参考
- **内容补充**：能给我手头某个选题补事实或数据
- **可归档**：信号低、已经掌握、或重复

### 为什么核查是三态，不是两态

笔记匠给每条要点标注**来源类型**，核查官据此判定证据强度。这两个 agent 之间靠这个标记交接：

| 来源类型 | 含义 |
|---|---|
| `原文` | 工具提取或你提供的确定文本 |
| `OCR` | 图像 / 视频帧的文字识别结果 |
| `ASR` | 语音转写结果 |
| `Vision` | 模型对画面的语义描述 |

核查结果因此是三态：

| 状态 | 含义 | 能直接存进知识库吗 |
|---|---|---|
| 已核实（直接引用） | 出处在原文中存在，可定位 | 可以 |
| 已核实（转述源） | 出处在 OCR/ASR/Vision 产出中存在，但未回溯原始音画 | **需你自己回看确认** |
| 可疑 / 原文无依据 | 找不到出处，或表述超出原文 | 不进 |

**两态为什么不够**：看 [`examples/`](examples/) 里的真实案例。一条视频笔记写了「6289万热度」，出处是视频帧 OCR——但 OCR 原文里的"收款/点费"实为"收藏/点赞"的误识别，那些数字来自识别噪声。

两态下核查官只能标「已核实」，然后把风险塞进备注。而备注是你最容易跳过的地方。这条笔记进知识库后，"6289万热度"看起来就是一个已核实的数字。

三态把它标成**已核实（转述源）**，你就知道这条需要回看原始画面。不是它错了，是它的证据链上有一环是模型产出——你需要知道这件事，再决定值不值得花时间去核对。

**这套流程存在的全部理由，就是不让二手甚至三手转述的内容伪装成已验证的事实。**

### 目录结构

```
WebNote/
├── README.md                           # 中文文档 + 快速开始
├── README.en.md                        # English documentation
├── Webpage note workflow.md            # 流程理念与索引（细节指向各定义文件）
│
├── agents/                             # ★ 三个角色定义（唯一事实来源，平台无关）
│   ├── classifier.md                   #   归类师：四选一分类
│   ├── distiller.md                    #   笔记匠：提炼要点，标注出处与来源类型
│   └── verifier.md                     #   核查官：三态核查（必须全新上下文）
├── steps/                              # 调度器自执行的步骤卡（操作卡，无契约）
│   ├── collect.md                      #   采编主卡：媒体分类规则 + 路由
│   ├── collect-image.md                #   采编 · 图片分支
│   ├── collect-video-audio.md          #   采编 · 视频/音频三级回退
│   └── confirm.md                      #   确认：汇总规则 + 确认边界
├── .claude/agents/                     # 注册薄壳（按需复制到你的工具注册位）
│   ├── classifier.md                   #   只含工具白名单 + 指向 agents/
│   ├── distiller.md
│   └── verifier.md
│
├── skills/                             # 项目内置的 AI skill
│   ├── webnote-workflow/               # ★ 总编排 skill（AI 入口：资源索引 + 派发顺序）
│   │   └── SKILL.md
│   └── web-archive/                    # 防复制页 / 云文档 / 懒加载长文无损拓存
├── prompts/                            # 开箱即用的入口提示词
│   ├── 入口提示词-全自动.md             # 有子代理能力的工具
│   └── 入口提示词-单对话框.md           # 纯聊天界面（三段式）
│
├── examples/                           # 一次完整运行的全部产出，建议先看
│   └── 2026-09-03-端到端验收/
│
├── tools/                              # 采编工具（渐进式依赖，都可以不装）
│   ├── check-env.py                    # 环境自检，零依赖
│   ├── extract-document.py             # PDF/DOCX 文本提取
│   ├── extract-webpage.py              # BrowserSkill 图文页面提取
│   ├── extract-video-text.py           # BrowserSkill 视频页面提取
│   ├── extract-video-asr.py            # 视频 ASR 语音转写（faster-whisper）
│   ├── extract-video-frames.py         # 视频画面采集（抽帧+OCR+Vision，需 Key）
│   ├── ds_vision.py                    # DeepSeek Vision 多图理解
│   ├── extract-image-ocr.py            # 图片本地 OCR（RapidOCR）
│   ├── extract-xhs.py                  # 小红书笔记拉取（需 Cookie）
│   └── run-xhs-note.py                 # 小红书单条笔记流水线
│
├── docs/                               # 外部工具文档
│   ├── BrowserSkill Installation Guide.md
│   └── BrowserSkill Command Reference.md
├── posts/                              # 可发布到博客平台的内容
├── runs/                               # 每次运行的产出（.gitignore 忽略）
│   └── YYYY-MM-DD-主题/
│       ├── 00-采编清单.md               # 调度器产出
│       ├── 01-整理清单.md               # 归类师产出
│       ├── 02-笔记.md                   # 笔记匠产出
│       ├── 03-核查表.md                 # 核查官产出
│       └── 04-待确认提案.md             # 调度器产出
└── LICENSE                             # MIT
```

**`agents/` 里的三份文件是角色定义的唯一事实来源。** 派发子代理时把文件交给它，不要凭记忆复述——复述最容易漏掉的是铁律，而铁律恰恰是不能漏的部分。每个文件头部有 frontmatter 契约（`context` / `reads` / `writes` / `forbidden`）。

**`agents/` 与 `steps/` 是流程资产，归项目根，不属于任何 skill 的私有实现。** `skills/webnote-workflow/SKILL.md` 只是路由卡，通过相对项目根的路径指向它们。

**注册薄壳（`.claude/agents/`）**：如果你想在支持 subagent 注册的工具里，让角色独立性由**工具机制**保证（而不是靠提示词恳求），把 `.claude/agents/` 里对应文件复制到该工具的注册位（如 WorkBuddy 的 `~/.workbuddy/agents/`、Claude Code 的 `.claude/agents/`）。薄壳只含工具白名单——例如核查官只给只读工具 + 只允许写自己的 `03-核查表.md`，从机制上保证它改不了笔记。角色定义本身不复制，始终指向 `agents/` 唯一事实来源。

### 使用方法

#### 0. 前置准备

**先跑环境自检**（建议，几秒钟）：

```bash
python tools/check-env.py
```

它会列出当前可用能力、缺什么、怎么补。缺的能力只影响对应媒体，不会让流程失败。

**然后准备正文或原页面**（工具自选）：

普通页面可以手动保存正文；防复制页、云文档或懒加载长文可直接走 `web-archive` 分支，通过 CDP 读取渲染后的 DOM 并按块重建。只复用用户已有登录态，不绕过付费墙、账号权限或验证码。

- **手动复制粘贴**：最稳，零依赖
- **Obsidian 网页剪藏 / 简悦 / Cubox / Readwise Reader** 等稍后读工具
- **BrowserSkill（可选）**：腾讯开源的浏览器桥接，可操控你已登录的浏览器读取页面，适合需要登录态的批量抓取（[安装指南](docs/BrowserSkill%20Installation%20Guide.md)）。**并非必需**，只是其中一种方式

**可选：若要用视频画面采集**（教程/课程/录屏类视频，提取画面文字与语义），需额外准备：

```bash
export DEEPSEEK_API_KEY="sk-xxx"   # 云端 DeepSeek Vision，绝不写进代码 / 提交 git
```

该能力为**可选增强**：不用则整个工作流完全不依赖 AI 做采集（见"采编"说明）。仅画面采集涉及调用云端模型，其余提取均为本地/确定性工具。

#### 执行模式（三种输出契约）

完整编排见 [`skills/webnote-workflow/SKILL.md`](skills/webnote-workflow/SKILL.md)，这里只列要点：

**模式 A · 多 Agent（工具支持 subagent 时，推荐）**：调度器（主会话）执行采编与确认，创建 3 个独立 subagent：

| 步 | 派发时交给它 | 上下文要求 |
|---|---|---|
| 归类师 | `agents/classifier.md` | 独立上下文 |
| 笔记匠 | `agents/distiller.md` | 独立上下文 |
| 核查官 | `agents/verifier.md` | **全新，与笔记匠零共享** |

核查官不能是笔记匠——自己查自己查不出编造内容。

**模式 B · 单对话框分段（无 subagent 能力时的降级）**：同对话完成采编 + 归类 + 提炼 → **停下**，要求用户把产物与原文带到**新对话**核查 → 核查表带回后确认。

**模式 C · 无损拓存**：防复制页、钉钉/飞书云文档、登录态长文或懒加载页面，使用 `skills/web-archive/SKILL.md`，经 DOM 探针、分窗采集、块级去重、阅读顺序恢复和 Markdown 渲染后落地。该模式不摘要、不改写、不进入归类与笔记匠；如果用户还要知识笔记，先完成无损存档并核验，再单独提炼。

> 核查必须独立（新 subagent 或新对话），否则查不出自己编的内容。
> 若实在无法开新对话，按 `agents/verifier.md` 的「降级声明」要求显式标注——**不声明，就是在用一份看起来合规的表格掩盖风险**。

#### 1. 文件流水线

五个文件并列写入 `runs/<本次子目录>/`，调度器（主会话） + 3 个 subagent 接力。原文不复制、不移动，仅在清单中记录来源路径。多次运行互不覆盖。

输入可用 JSON 格式引用原文路径（不复制）：

```json
[
  {
    "id": "p01",
    "title": "某数据库年度报告",
    "domain": "example.org",
    "url": "https://example.org/db-report-2026",
    "source_path": "E:/notes/webpages/db-report-2026.md"
  },
  {
    "id": "p02",
    "title": "上下文工程演讲",
    "domain": "youtube.com",
    "url": "https://youtube.com/watch?v=xxxx",
    "source_path": null
  }
]
```

`source_path` 为 `null` 即表示无正文。

### 确认边界

AI 出提案，你按确认键。判断标准：**这个动作如果错了，撤得回来吗？**

| 必须停在"待确认" | 可以让调度器（主会话）直接干 |
|------------------|------------------|
| 删除 / 归档 / 移动资料 | URL 正则分类、调用 CLI 工具（含画面采集；其云端 Vision 调用为只读理解，非落地动作） |
| 发布（文章 / 社交媒体） | 读、归类、提要点 |
| 改长期记忆 / 知识库 | 列清单、出提案、给建议 |

**一句话：AI 可以无限地"想"和"建议"，但凡要"落地动手"，停在你这道闸前。**

### 本地环境约定（本机，不影响他人）

- **ASR（`tools/extract-video-asr.py`）用专用环境**：`.venv-asr`（Python 3.11 + faster-whisper + yt-dlp），已进 `.gitignore`。
  系统 conda 里是 Python 3.13 且没装 `faster_whisper`/`ctranslate2`，直接跑会 `ModuleNotFoundError`。
  ```bash
  .venv-asr\Scripts\python.exe tools\extract-video-asr.py <视频URL>
  ```
- **模型必须走本地快照**：默认 `large-v3`，由 `resolve_model_dir()` 解析成
  `E:\data\models\HuggingFace\hub\models--Systran--faster-whisper-large-v3` 的 snapshot 目录再传给 `WhisperModel`。
  只写模型名仍会联网校验；`large-v3-turbo` 的上游仓库已私有化，按名字加载会 401。
- **git 推送走 Windows 侧**：WSL 里 `~/.ssh` 为空，`git push` 会卡在 publickey 等待。
  在 Windows 终端（或 `cmd.exe /c "cd /d E:\Projects\personal\WebNote && git push"`）执行，密钥在 `C:\Users\stars\.ssh`。

### 参考

- 设计参考：[Agent OS 的第一课：会分工，才会用 Agent](https://www.axtonliu.ai/newsletters/ai-2/posts/agent-os-workstation-division)
- 工具依赖：[BrowserSkill（腾讯开源）](https://github.com/Tencent/BrowserSkill)

### 许可证与致谢

- 本仓库的文档与提示词采用 **MIT** 许可证，详见 [LICENSE](LICENSE)。你可自由使用、修改、再分发。
- 设计理念致谢 [Axton Liu《Agent OS 的第一课：会分工，才会用 Agent》](https://www.axtonliu.ai/newsletters/ai-2/posts/agent-os-workstation-division)。

---
