# WebNote · 网页笔记工作流

> 把「采集 → 分类 → 提炼 → 核查 → 确认」拆成**调度器（主会话） + 三个独立 Agent**。确定性的事主会话自己干，只有真正需要独立判断的才交给 subagent。

[English](README.en.md) · [给 AI 的入口](AGENTS.public.md) · [架构](docs/architecture.md)

## 这是什么

一套**以"可信"为核心**的网页内容整理流程：目标不是更快地产出，而是更可靠地把网页内容变成自己的知识。

它只解决一个问题：**别让二手甚至三手转述的内容伪装成已验证的事实。**

## 快速开始

### 零依赖也能用

核心价值是**流程设计与角色定义**，不是那些 Python 脚本。没有脚本，你把正文贴给 AI，整条流程照样跑得通。

| 你要处理 | 额外需要 |
|---|---|
| 图文（正文你自己提供） | 零依赖 |
| PDF / Word | `pip install pypdf python-docx` |
| 图片文字 | `pip install rapidocr-onnxruntime` |
| 视频语音 | `pip install faster-whisper` + `ffmpeg` |
| 图片/视频画面理解 | 上面几项 + `DEEPSEEK_API_KEY` |

不确定现在能跑什么：`python tools/check-env.py`（纯标准库，先跑再装）。缺的能力只影响对应媒体，不会让流程失败。

### 三条使用路径

| 路径 | 适合 | 做法 |
|---|---|---|
| **A 装配技能** | 有项目级 skill 的工具 | 把 `<本仓>/skills/` 链进工具的 skills 目录，之后自然对话即触发 |
| **B 提示词** | 任何 AI | 把 [`AGENTS.public.md`](AGENTS.public.md) 和你的内容一起交给它 |
| **C 手动** | 想逐步控制 | 按 [`steps/`](skills/webnote-workflow/references/steps/) 五步走，每步只加载当步定义 |

工具没有 subagent 能力（网页版 ChatGPT / Claude）：用模式 B 三段式，提示词在 [`degraded-single-dialog.md`](skills/webnote-workflow/references/degraded-single-dialog.md)。**三段必须分三个对话**——核查不能自己查自己。

### 起一次运行

```bash
cp -r runs/_template runs/2026-11-09-主题     # 表头是硬契约，别改
```

五个文件由 主会话 / 归类师 / 笔记匠 / 核查官 / 主会话 依次填。原文不复制、不移动，只在 `00` 里记来源路径。

## 为什么核查是三态

笔记匠给每条要点标**来源类型**（`原文` / `OCR` / `ASR` / `Vision`），核查官据此判定证据强度：

| 状态 | 含义 | 能直接进知识库吗 |
|---|---|---|
| 已核实（直接引用） | 出处在原文里有，可定位 | 可以 |
| 已核实（转述源） | 出处是 OCR/ASR/Vision 产出，未回溯原始音画 | **需你自己回看** |
| 可疑 | 找不到出处，或表述超出原文 | 不进 |

两态为什么不够：一个真实案例里，笔记写了「6289万热度」，出处是视频帧 OCR——而 OCR 原文里的"收款/点费"实为"收藏/点赞"的误识别。两态下核查官只能标「已核实」，把风险塞进备注，而备注是最容易被跳过的地方。三态把它标成「已核实（转述源）」，你就知道证据链上有一环是模型产出。

案例与论证：[`docs/history/`](docs/history/2026-09-03-two-state-example/)。**注意那是历史存档，格式已废弃，勿照抄表头。**

## 目录结构

```
WebNote/
├── AGENTS.public.md      # 给 AI 的公开入口（AGENTS.md 的脱敏生成物）
├── bot.yaml              # 只记一件事：外部技能的上游与 commit
├── agents/               # 三个角色定义，平台无关，唯一真源
│   ├── classifier.md     #   四选一分类
│   ├── distiller.md      #   提炼 3~5 条要点，标出处与来源类型
│   └── verifier.md       #   三态核查（必须全新上下文）
├── skills/               # SKILL.md 只做路由，细则在 references/
│   ├── webnote-workflow/ #   总编排 + steps/ 五步细则 + 模式 B 提示词
│   ├── web-archive/      #   防复制页 / 云文档 / 懒加载长文的无损拓存
│   ├── image-extract/    #   图片 OCR + 画面语义
│   ├── video-extract/    #   视频 ASR + 抽帧
│   └── browser-skill/    #   外部技能副本（Tencent/BrowserSkill，勿手改）
├── runs/
│   ├── _template/        # ★ 五份空骨架：产出格式的唯一契约，只读
│   └── YYYY-MM-DD-主题/  #   一次运行（本地，不进 git）
├── tools/                # 采编加速器 + 自检脚本（依赖都可选）
│   ├── check-env.py      #   环境自检
│   ├── check-links.py    #   Markdown 相对链接
│   ├── check_vendor.py   #   外部技能副本是否还是上游那份
│   ├── sync-agents-public.py  # 由 AGENTS.md 生成公开版
│   └── extract-*.py      #   文档 / 网页 / 视频 / 图片 提取
├── tests/                # 仓库不变量（进 CI）
│   └── manual/           #   需要真实浏览器的回归 + 离线夹具（不进 CI）
├── docs/
│   ├── architecture.md   # 现行架构
│   ├── decisions.md      # 决策记录
│   ├── versions/         # 已发表旧版（正文原样）
│   └── history/          # 历史存档：格式已废弃，只用来解释规则来由
├── memory/               # 长期记忆（本地私有，不进 git）
└── .env.example          # 环境变量键名（真值放 .env）
```

## 执行模式

| 模式 | 何时用 | 分工 |
|---|---|---|
| **A 多 Agent** | 工具支持 subagent（推荐） | 主会话做采编与确认，三个 subagent 依次做分类 / 提炼 / 核查；核查官必须与笔记匠零共享上下文 |
| **B 单对话框** | 工具开不了新会话 | 同对话做采编+分类+提炼 → **停下** → 用户带产物到新对话核查 → 带回确认 |
| **C 无损拓存** | 防复制页 / 云文档 / 登录墙长文 | 只拓存不摘要；要笔记就拓存核验后再单独提炼 |

核查是安全闸门：**自己查自己等于没查**。真开不了新对话，按 `agents/verifier.md` 的降级声明显式标注——不声明，就是用一份看起来合规的表掩盖风险。

## 确认边界

AI 出提案，你按确认键。判据：**这个动作错了，撤得回来吗？**

| 必须停在「待确认」 | 主会话可直接做 |
|---|---|
| 删除 / 归档 / 移动资料 | URL 分类、调 CLI 工具、读与提炼要点 |
| 发布（文章 / 社交） | 列清单、出提案、给建议 |
| 改长期记忆 / 知识库 | — |

**AI 可以无限地"想"和"建议"，但凡要"落地动手"，停在这道闸前。**

## 本地环境约定（本机，不影响他人）

- **ASR 用专用环境**：`.venv-asr`（Python 3.11 + faster-whisper + yt-dlp），已 gitignore。系统 Python 3.13 没有 `faster_whisper`，直接跑会 `ModuleNotFoundError`。
- **模型走本地快照**：默认 `large-v3`，由 `resolve_model_dir()` 从 HuggingFace 缓存解析后传给 `WhisperModel`；只写模型名会联网校验，`large-v3-turbo` 上游已私有化，按名加载会 401。
- **git 推送走 Windows 侧**：WSL 里可能没有 ssh 密钥，`git push` 会卡在 publickey。

## 参考与许可

- 设计参考：[Agent OS 的第一课：会分工，才会用 Agent](https://www.axtonliu.ai/newsletters/ai-2/posts/agent-os-workstation-division)（本仓只借鉴"分工隔离 / 独立核查 / 确认闸门"三层思路，文档与提示词均独立撰写）
- 外部工具：[BrowserSkill](https://github.com/Tencent/BrowserSkill)（腾讯开源）
- 文档与提示词采用 **MIT**，见 [LICENSE](LICENSE)
