<!-- 由 tools/sync-agents-public.py 从仓库根的 AGENTS.md 生成，勿手改。 -->
<!-- 私有内容（本机路径、账号、记忆库位置、汇报口径）已剔除。 -->

# WebNote · 唯一入口

本仓是「网页笔记工作流」的唯一来源：角色、流程、技能、工具、范例都在这里。
不存在第二份角色目录——要改流程就改本仓，本文件是 agent 的入口。

按下面顺序读，不要凭记忆复现任何定义。

## 本项目提供什么（任何工具通用）

下面这段由 `bot.yaml` 生成，是本仓全部能力的清单：

<!-- bot:start 由 bot.yaml 生成，勿手改；改完跑 python tools/doctor.py --wire -->

角色（需要时读定义文件，按其 reads / writes / forbidden 执行）：

| 角色 | 定义 | 可写 | 独立上下文 |
|---|---|---|---|
| `classifier` | `agents/classifier.md` | `runs/*/01-整理清单.md` | 否 |
| `distiller` | `agents/distiller.md` | `runs/*/02-笔记.md` | 否 |
| `verifier` | `agents/verifier.md` | `runs/*/03-核查表.md` | 必须 |

技能（开工先读对应 SKILL.md，只做路由）：

- `webnote-workflow` → `skills/webnote-workflow/SKILL.md`
- `web-archive` → `skills/web-archive/SKILL.md`
- `image-extract` → `skills/image-extract/SKILL.md`
- `video-extract` → `skills/video-extract/SKILL.md`
- `xhs-note` → `skills/xhs-note/SKILL.md`

流程：
- `lean`（精简流程）：取原文 → 分类 → 提炼 → 核查 → 确认
- `full`（完整流程）：采编清单 → 整理分类 → 笔记提炼 → 独立核查 → 人工确认

命令：
- `python tools/doctor.py`  — doctor
- `python tools/doctor.py --wire`  — wire
- `python tools/doctor.py --check`  — check
- `python tools/check-env.py`  — check_env
- `python -m pytest tests -q`  — test
<!-- bot:end -->

**怎么用（不依赖任何工具的注册表）：**

1. 需要某个角色时，读上表里它的定义文件，按 `reads` / `writes` / `forbidden` 执行。
   你的工具若不支持子 agent，就自己扮演该角色，**一次只扮一个**。
2. 标「必须独立上下文」的角色，必须在**不携带上文**的情况下执行（新会话，或明确声明
   「以下判断不参考我此前的结论」）。做不到就按 `agents/verifier.md` 的降级声明显式标注。
3. 表里的「可写」是硬边界：越界的一律不写，把内容作为回复交回主 agent。
4. 想拿到工具级硬约束（工具白名单、写入拦截、真隔离），跑 `python tools/doctor.py --wire`；
   只想知道本工具缺什么，跑 `python tools/doctor.py`。

## 目录职责

| 路径 | 是什么 | 什么时候读 |
|---|---|---|
| `skills/` | 五个技能：`webnote-workflow`（总编排）、`web-archive`、`image-extract`、`video-extract`、`xhs-note` | 开工先读对应 `SKILL.md`（只做路由），细则在 `references/` |
| `skills/webnote-workflow/references/steps/` | 五步流程细则（collect / collect-image / collect-video-audio / collect-web-archive / confirm） | 手动流水线（路径 C）逐条读 |
| `agents/` | 三个子角色：`classifier`（整理分类）、`distiller`（提炼笔记）、`verifier`（独立核查） | 派发 subagent 前读，把**文件路径**交给它 |
| `bot.yaml` | 能力清单真源：角色/skill/流程/命令/各工具注册面 | 改角色注册信息、增删技能时 |
| `.claude/agents/` | Claude Code 的注册面，**生成物**（`bot.yaml` + `agents/*.md` → 勿手改） | 只由 `doctor.py --wire` 写入 |
| `memory/` | 长期记忆：跨 run 提炼的结论，`long-term/` 一条一文件 + `index.md` 索引 | 开工前扫索引；收尾时沉淀新结论（用户点头后写） |
| `memory/long-term/` | 单条记忆（格式见 `memory/README.md`） | 只读与本次相关的那几条，不整目录读 |
| `tools/` | 采编加速器（Python 标准库为主，可选依赖按需装）+ `doctor.py`（自检/接线）+ `hooks/guard_write.py`（写入守卫）+ `sync-agents-public.py` | 采集、转写、拓存时 |
| `tools/_migrations/` | 一次性维护脚本（已跑过，不进运行时） | 只有做结构迁移、查断链、脱敏示例时才用 |
| `tests/` | 仓库不变量（pytest）+ web-archive 真机回归 + 离线夹具 | 改完结构或流程后跑 |
| `examples/` | 一次完整运行（三态改造前）的全部产物，**冻结不更新** | 想知道产出长什么样 |
| `runs/<日期-主题>/` | 一次运行的五个产物（本地，`gitignore` 忽略） | 只在本次运行内读 |
| `runs/_template/` | 新 run 的空骨架（**进 git、只读**；表头是硬契约，测试会比对） | 起新 run 时整个目录复制成 `runs/<日期-主题>/`，再填 |
| `docs/` | 架构 `architecture.md`（v3 现行）、历史版本 `versions/`、决策 `decisions.md`、外部手册 `vendor/` | 理解整体设计 / 追溯版本 |
| `config/` | 运行时默认参数（公开，不含机器路径） | 改阈值、媒体后缀、核查规则时 |
| `persona/` | 角色头像等原件（本地私有，不入 git） | 一般不用读 |

`agents/`、`skills/webnote-workflow/references/steps/`、`tools/` 在运行中是权威，与 `README.md` 的表述冲突时以它们为准；
与**用户最新直接指令**冲突时以用户为准。

## 三条使用路径

- **A 装配技能**：把 `<本仓>/skills/` 链进工具的 skill 目录（Claude Code → `.claude/skills/`；Codex、pi 等按各自机制），之后自然对话即触发。
- **B 提示词**：把 `AGENTS.public.md` 与内容一起交给 AI（它本身就是入口说明）。没有 subagent 能力时用模式 B 三段式，提示词在 `skills/webnote-workflow/references/degraded-single-dialog.md`。
- **C 手动**：按 `skills/webnote-workflow/references/steps/` 五步走，每步只加载当步定义。

先跑 `python tools/check-env.py`：缺依赖只影响对应媒体（PDF OCR / 视频转写），图文流程零依赖可用。

## 硬约束

1. **技能优先，不凭记忆简化。** 这类任务开头加载 `webnote-workflow`；视频/音频另加 `video-extract`；防复制页、钉钉/飞书云文档、登录墙、懒加载长文另加 `web-archive` + `skills/webnote-workflow/references/steps/collect-web-archive.md`。不要因为"看起来简单"跳过技能里的步骤。
2. **范围**：只做内容提取与笔记整理；无关的开发/运维工作不在本角色内，除非用户明确要求。
3. **核查独立**：核查者必须是全新上下文，且不是笔记撰写者。做不到就按 `agents/verifier.md` 的降级声明**显式标注**，不要用一份看起来合规的表掩盖。
4. **三条铁律**：① 正文不凭空编——提取不到就如实写「无」；② 核查独立；③ 不改写用户已有文件，命名冲突就用来源/日期后缀或另起一份；原始输入只读。
5. **凭据只查可用性，不读不写不报值。**

## 交付模式（写之前先选一个）

1. **仅无损拓存**：把渲染后的结构存到 Resources，不摘要、不改写。
2. **仅知识提取**：提取正文，提炼成 Knowledge 笔记。
3. **先拓存再提炼**：先把无损原文落好并核对，再从**已存的那份**派生笔记。

无损拓存与知识笔记是两个独立契约：拓存件不得被悄悄摘要或重组；笔记不得替代原文。

## 改本仓的约定

1. `SKILL.md` 只做路由，细则放同目录 `references/`。
2. 新增媒体能力：脚本进 `tools/`，并在 `tools/check-env.py` 登记「缺什么、怎么补」。
3. 改流程：同步更新 `skills/webnote-workflow/references/steps/`、`README.md` 能力表、受影响技能，以及本文件；改完跑 `python tools/sync-agents-public.py`（重新生成公开版）与 `python -m pytest tests -q`（不变量）。
4. 环境变量只把**键名**写进 `.env.example`，真值放 `.env`（已 gitignore）；任何真实路径、Cookie、Key 不进 `AGENTS.md` 以外的公开文件。
4. `agents/` 是角色定义唯一来源；`.claude/agents/` 的同名三份是带 frontmatter 的适配层，改正文时两边保持一致。
5. 不提交生成物与本机状态：`runs/`、`.workbuddy/`、`.memory/`、`.venv-asr/`、临时音视频。
6. **本仓是公开仓**：只提交脱敏内容。私有路径、账号、密钥一律写在 `<!-- private:start -->` 块里，这些块不会进入公开版。

## 边界

- 不做绕过付费墙/登录墙的抓取；只处理用户已授权的页面。
- 不把用户内容上传到本仓；产物留在本地 `runs/` 与知识库。
- 提取失败要说失败，不补写。

## 自检

- `python tools/doctor.py` —— 本工具能用什么、缺什么（角色 / 技能 / 生成物 / 写入守卫）
- `python tools/doctor.py --wire` —— 生成注册面与挂上守卫（幂等；改完 `bot.yaml` 或 `agents/*.md` 后跑）
- `python tools/doctor.py --check` —— 生成物是否与真源一致（手改 `.claude/` 会被它打回）
- `python tools/check-env.py` —— 当前机器能跑哪些媒体分支
- `python tools/sync-agents-public.py --check` —— 公开版是否与私有版一致（漂移返回非 0）
- `python -m pytest tests -q` —— 仓库不变量（角色齐全、无私有路径泄漏、守卫拦截生效）

**改角色时只改两处**：`agents/<name>.md`（定义与 `description`）与 `bot.yaml`（工具白名单 / `write_scope` / 是否需要独立上下文）；然后 `--wire`。生成物永远不要手改。
