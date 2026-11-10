<!-- 由 tools/sync-agents-public.py 从仓库根的 AGENTS.md 生成，勿手改。 -->
<!-- 私有内容（本机路径、账号、记忆库位置、汇报口径）已剔除。 -->

# WebNote · 唯一入口

本仓是「网页笔记工作流」的唯一来源：角色、流程、技能、工具都在这里。
不存在第二份角色目录——要改流程就改本仓，本文件是 agent 的入口。

按下面顺序读，不要凭记忆复现任何定义。

## 本项目提供什么（任何工具通用）

**流水线**——五步的定义全在 `skills/webnote-workflow/steps/`，**文件名就是顺序**：

| 步 | 文件 | 角色 | 可写 | 上下文 |
|---|---|---|---|---|
| 1 采编 | `steps/00-collect.md` | 调度器自己 | `runs/*/00-采编清单.md` | 主会话 |
| 2 归类 | `steps/01-classify.md` | `classifier` | `runs/*/01-整理清单.md` | `isolated`（建议独立） |
| 3 提炼 | `steps/02-distil.md` | `distiller` | `runs/*/02-笔记.md` | `isolated`（建议独立） |
| 4 核查 | `steps/03-verify.md` | `verifier` | `runs/*/03-核查表.md` | `fresh`（必须全新） |
| 5 确认 | `steps/04-confirm.md` | 调度器自己 | `runs/*/04-待确认提案.md` | 主会话 |

路径相对 `skills/webnote-workflow/`。每个文件头部的 frontmatter 是契约（`context` / `reads` / `writes` / `forbidden` / `produces` / `format_needles`），按它执行。

**技能**——开工先读对应 `SKILL.md`（只做路由，细则在 `references/`）：

- `webnote-workflow` → `skills/webnote-workflow/SKILL.md`（总编排）
- `web-archive` → `skills/web-archive/SKILL.md`（防复制页 / 云文档无损拓存）
- `image-extract` → `skills/image-extract/SKILL.md`（图片 OCR + 画面语义）
- `video-extract` → `skills/video-extract/SKILL.md`（视频 ASR + 抽帧）

**外部技能**（真源不在本仓，读可以，别改内容）：

- `skills/browser-skill` ← https://github.com/Tencent/BrowserSkill @ `e380cbc`（快照 2026-11-09，`SKILL.md` + `references/`；来源与刷新见 `bot.yaml` 的 `vendored:`）

**产出格式**：定义在各个 `steps/0N-*.md` 的 `format_needles` 里；`runs/_template/` 是与之逐条一致的空骨架。起新 run 整目录复制，表头不改。

**怎么用（不依赖任何工具的注册表）：**

1. 需要某个角色时，读它的定义文件，按契约执行。你的工具不支持子 agent，就自己扮演，**一次只扮一个**。
2. `context: fresh` 的步骤必须在不携带上文的情况下执行（新会话，或明确声明「以下判断不参考我此前的结论」）。做不到就按 `steps/03-verify.md` 的降级声明**显式标注**。
3. 表里的「可写」是硬边界：越界的一律不写，把内容作为回复交回主 agent。

> 这套结构只依赖一件事：**能读文件就够**。工具支持 skill / subagent 注册时可以更省事，但不注册不影响流程成立——注册只是把"靠遵守"变成"靠机制"。

## 目录职责

| 路径 | 是什么 | 什么时候读 |
|---|---|---|
| `skills/` | 四个自有技能 + 一个外部副本 | 开工先读对应 `SKILL.md`，细则在 `references/` |
| `skills/webnote-workflow/steps/` | **流水线唯一定义**：`00`–`04` 五个步骤文件（文件名即顺序），每份自带契约与产出格式 | 手动流水线按编号逐条读 |
| `skills/webnote-workflow/steps/branches/` | 采编分支卡：`image` / `video-audio` / `web-archive` | 只在 `00-collect.md` 判断命中时读 |
| `skills/webnote-workflow/references/degraded-single-dialog.md` | 模式 B 三段式（无 subagent 时） | 工具开不了新会话时 |
| `skills/browser-skill/` | 外部技能副本（`bsk` CLI 说明），**勿手改** | 只在改 `extract-webpage.py` 调用方式时读 |
| `bot.yaml` | 只记一件事：外部技能的上游 / commit / 快照 / 文件数 | 刷新副本（`check_vendor.py --pull`）或查"这份是哪一代" |
| `tools/` | 采编加速器（标准库为主，可选依赖按需装）+ 自检脚本 | 采集、转写、拓存、自检时 |
| `tools/_migrations/` | 一次性维护脚本（已跑过，不进运行时） | 只有做结构迁移或脱敏历史件时才用 |
| `tests/` | 仓库不变量（pytest，进 CI） | 改结构、改表头、改生成逻辑后跑 |
| `tests/manual/` | 需要真实浏览器的回归与离线夹具（不进 CI） | 改动 `web-archive` 脚本后手动跑 |
| `runs/_template/` | 新 run 的空骨架（**进 git、只读**；表头是硬契约） | 起新 run 时整目录复制成 `runs/<日期-主题>/` |
| `runs/<日期-主题>/` | 一次运行的五个产物（本地，gitignore 忽略） | 只在本次运行内读 |
| `docs/` | 架构 `architecture.md`（现行）、`versions/` 已发表旧版、`decisions.md` 决策、`history/` 历史存档（勿照抄） | 理解整体设计 / 追溯缘由 |

`skills/webnote-workflow/steps/`、`tools/`、`docs/architecture.md` 在运行中是权威，与 `README.md` 表述冲突时以它们为准；与**用户最新直接指令**冲突时以用户为准。

## 三条使用路径

- **A 装配技能**：把 `<本仓>/skills/` 链进工具的 skill 目录（Claude Code → `.claude/skills/`；Codex、pi 等按各自机制），之后自然对话即触发。
- **B 提示词**：把 `AGENTS.public.md` 与内容一起交给 AI（它本身就是入口说明）。没有 subagent 能力时用模式 B 三段式。
- **C 手动**：按 `skills/webnote-workflow/steps/` 的 `00`–`04` 顺序走，每步只加载当步文件。

先跑 `python tools/check-env.py`：缺依赖只影响对应媒体，图文流程零依赖可用。

## 硬约束

1. **技能优先，不凭记忆简化。** 这类任务开头加载 `webnote-workflow`；视频/音频另加 `video-extract`；防复制页、钉钉/飞书云文档、登录墙、懒加载长文另加 `web-archive` + `steps/branches/web-archive.md`。不要因为"看起来简单"跳过技能里的步骤。
2. **范围**：只做内容提取与笔记整理；无关的开发/运维工作不在本角色内，除非用户明确要求。
3. **核查独立**：核查者必须是全新上下文，且不是笔记撰写者。做不到就按 `steps/03-verify.md` 的降级声明**显式标注**，不要用一份看起来合规的表掩盖。
4. **三条铁律见 [`docs/architecture.md`](docs/architecture.md#三条不可逾越)**（正文不凭空编 / 核查独立 / 落地必待确认）——此处不重写。原始输入只读，命名冲突用来源或日期后缀，另起一份。
5. **凭据只查可用性，不读不写不报值。**

## 交付模式（写之前先选一个）

1. **仅无损拓存**：把渲染后的结构存到 Resources，不摘要、不改写。
2. **仅知识提取**：提取正文，提炼成 Knowledge 笔记。
3. **先拓存再提炼**：先把无损原文落好并核对，再从**已存的那份**派生笔记。

无损拓存与知识笔记是两个独立契约：拓存件不得被悄悄摘要或重组；笔记不得替代原文。

## 改本仓的约定

1. `SKILL.md` 只做路由，细则放同目录 `references/`。
2. 新增媒体能力：脚本进 `tools/`，并在 `tools/check-env.py` 登记「缺什么、怎么补」。
3. **改产出格式要动两处**：`runs/_template/<文件>` 与对应步骤文件的 `format_needles`；`test_template_matches_step_card` 会比对，只改一边就红（其余位置自动跟随，不要另抄）。
4. 改流程：同步更新 `steps/`、`README.md` 的能力表、受影响技能，以及本文件；改完跑 `python tools/sync-agents-public.py` 与 `python -m pytest tests -q`。
5. 环境变量只把**键名**写进 `.env.example`，真值放 `.env`（已 gitignore）；任何真实路径、Cookie、Key 不进公开文件。
6. 不提交生成物与本机状态：`runs/`、`.workbuddy/`、`.venv-asr/`、临时音视频。
7. **运行异常要留痕**：每次运行把工具失败、参数踩坑、人工补救写进该 run 的 `00-采编清单.md`「运行异常」节；同一异常出现第二次，就升级成一条测试或一条 `docs/decisions.md`，别留在 run 里自生自灭。
8. **本仓是公开仓**：只提交脱敏内容。私有路径、账号、密钥一律写在 `<!-- private:start -->` 块里，这些块不会进入公开版。

## 边界

- 不做绕过付费墙/登录墙的抓取；只处理用户已授权的页面。
- 不把用户内容上传到本仓；产物留在本地 `runs/` 与知识库。
- 提取失败要说失败，不补写。

## 自检

- `python tools/check-env.py` —— 当前机器能跑哪些媒体分支
- `python tools/check-links.py` —— 全仓 Markdown 相对链接
- `python tools/check_vendor.py` —— 外部技能副本是否还是上游那份（`--online` 才联网）
- `python tools/sync-agents-public.py --check` —— 公开版是否与私有版一致
- `python -m pytest tests -q` —— 仓库不变量（表头契约、泄漏扫描、外部技能完整性）
