# 项目决策记录

> 从 SemanticMemory 迁入（2026-10-31）。原 claim 已归档，`--include-history` 仍可查。

## 外部技能：副本进仓、真源记在 bot.yaml，exe 版本号不算真源

**问题**：`browser-skill` 来自腾讯的 `Tencent/BrowserSkill`（MIT），既不由本仓维护，也不是技能库维护的——技能库那份是 2026-09-30 从 bsk 产物人工搬进去的快照。链条是三跳：上游仓库 → `crates/bsk-cli/skill/` → 技能库 → 本仓 `skills/browser-skill/`。`.skillshare/config.yaml` 只说得清最后一跳。

**发现**：查上游时发现我们落后一代。上游 2026-11 起把单文件 `SKILL.md`（229 行 / 11,406 B）改成「主体 131 行 + `references/` 13 个文件 / 81 KB」，上游 `crates/bsk-cli/src/skill_install/` 里的 `legacy-digests.txt`、`provenance.rs`、`sync.rs` 就是这次布局迁移的痕迹。

**决定**：

1. **真源写进 `bot.yaml` 的 `vendored:` 段**（`upstream` / `subdir` / `ref`（完整 commit sha）/ `snapshot` / `layout`），因为 `.skillshare` 只描述「从哪里 copy」，说不清「上游是哪一代」。
2. **不用 `bsk --version` 当基准**：别人机器上不一定有那个 exe，而且 exe 与仓库本来就可能不同代。
3. **检查分两层**：`tools/check_vendor.py`（离线：副本存在、是真目录不是链接、文件数、是��与 include 对得上；进 CI）与 `--online`（拉上游 tree API 逐个比 blob sha；联网、可能限流，不进 CI）。
4. **副本按上游布局整体覆盖**，不只换 `SKILL.md`——主体里引用了每个 references 文件，只同步一半会让 agent 读到悬空引用（`test_vendored_references_all_reachable` 守着这条）。
5. **库那一跳保留**：skillshare 的 `include` 按 `<name>/SKILL.md` 找技能，上游是 `crates/bsk-cli/skill/SKILL.md`（目录名 `skill`），直连需要先改名，比中转更绕。同步时两份一起换，否则下次 `skillshare sync -p` 会把副本退回旧版。

**代价**：仓库多 88 KB 与 13 个文件；`check_vendor.py --online` 依赖 `gh` 或 `GITHUB_TOKEN`（匿名 API 会 403 限流）。

## 记忆分层：核心记忆进 AGENTS.md，长期记忆进 memory/

**问题**：`persona/SOUL.md` 与 `AGENTS.md` 内容重叠（身份、专职角色、硬约束、汇报格式各写一遍），且 SOUL 里的落库路径还是错的（`<知识库根>/vault/Resources/`（`vault/` 早已不存在））。同时没有任何地方沉淀"跨 run 的经验"——都散在 `runs/`（过程）和知识库（产出）里。

**决定**：

1. **核心记忆不单独建文件**，写进 `AGENTS.md` 的「核心记忆」小节（私有块内）。理由：它必须常驻上下文，多一个文件就多一次读取、多一个漂移点，而 `AGENTS.md` 本来就是被自动加载的那一份。`persona/SOUL.md` 内容并入后删除（原稿在归档包 `webnote-role-2026-11-09.tgz`）。
2. **长期记忆独立成 `memory/`**：`index.md` 一行一条做检索，`long-term/` 一条一文件（frontmatter 标 `date/topic/confidence/source`）。理由：记忆要按需取，整目录塞进上下文只会稀释注意力；一条一文件也让"索引腐烂"可被测试发现。
3. **角色与技能不做合并**：`agents/` 与 `skills/` 的位置是被工具机制钉住的（`skills/<name>/SKILL.md` 是发现约定，`AGENTS.md` 是入口文件名），搬家即失去自动发现。只有长期记忆没有任何约定，才需要人为给它一个目录。
4. 边界：`runs/` 是过程不是记忆；记忆只从 `03-核查表.md` 这类已核实的产物里提炼，且落盘要用户点头。角色（subagent）不得写记忆。

> 后续（2026-11-09）：`memory/` 已删除，跨 run 结论只落知识库，见下方「清减」条目。

**代价**：多一层目录与一条索引维护成本；换来"下次怎么做得对"有确定落点，且不用把整份历史塞进上下文。

## 角色分发：真源 + 生成物，写入边界挂在项目级 hook

**问题**：同一个角色定义要同时喂给多种 agent 工具，而各工具的注册面互不兼容；手写多份薄壳后，`description` 会漂移，且薄壳里写的 `permissions.allow/deny` 在 Claude Code 里根本不是可用字段（实测 CC 2.1.310 只解析 `name/description/prompt/tools/disallowedTools/model/effort/permissionMode/mcpServers/hooks/maxTurns/...`），"核查官只能写 03-核查表.md" 因此毫无机制保障。

**决定**：

1. 角色定义只有一处 —— `agents/<name>.md`（含 `description` 与 `context/reads/writes/forbidden` 契约），平台无关。
2. 注册信息只有一处 —— `bot.yaml`（`tools` / `disallowed_tools` / `write_scope` / `fresh_context`）。
3. `.claude/agents/*.md` 与 `.claude/settings.json` 是**生成物**，由 `tools/doctor.py --wire` 产出，CI 用 `--check` 打回手改。
4. 写入边界不依赖 agent frontmatter 的 `hooks`（实测不执行），改挂项目级 `PreToolUse`：`tools/hooks/guard_write.py` 读 payload 里的 `agent_type`，按 `bot.yaml` 的 `write_scope` 判定，越界 exit 2。

**代价/收益**：多一个生成步骤与一条 CI 断言；换来一份定义喂所有工具，且"越界写入"从提示词约束变成机制拦截（实测 verifier 写 `runs/x/02-笔记.md` 被拒、`runs/x/03-核查表.md` 放行）。

> 后续（2026-11-09）：注册面整体退役（`doctor.py`、写入守卫、`.claude/agents/`、`bot.yaml` 的 roles/skills/flows 全部删除）。原因见下方「清减」条目——它只对一家工具生效，换工具即失效。

## WebNote 架构决策：5 Agent 精简为主会话 + 3 subagent

不是每一步都需要独立的 AI 上下文。 确定性的事主会话自己干，只有真正需要独立判断的才创建 subagent：

- 原 claim：`decision-2b28f2c3553f`（已归档）
- 来源：`.backup/Memory-20261029/Decisions/WebNote架构决策-5Agent精简为主会话+3subagent.md`

## 网页知识提取核心能力直写 Obsidian

网页来源正文直接写入 Resources 对应来源目录，生成的知识笔记写入 Knowledge 对应域并关联 MOC。正常采集、提炼和落库不再逐条提案；内容必须来自实际页面或媒体，记录 URL、来源类型和限制。

- 原 claim：`rule-webnote-direct-write`（已归档）
- 来源：`.backup/Memory-20261029/Preferences/网页知识提取机器人-核心能力直写Obsidian.md`

## 2026-11-09 · 清减：删掉没有读者的机制，只留主链

**背景**：仓里 8,800 多行中约 1,400 行零收益，其中大半是同一周陆续加的：`config/default.yaml`（30 行，全仓 0 处读取）、`memory/`（48 行，索引 0 条记录）、`tests/fixtures` + `test-web-archive.ps1`（308 行，不进 CI）、`bot.yaml` 全量 + `doctor.py` + `.claude/agents` + 写入守卫（约 600 行，只对 Claude Code 生效）、小红书三件（466 行，四次运行 0 次用到）。

**决定**：

1. **删 `config/default.yaml`**：没有一个模块读它，`.env.example` 才是真正的键名契约。
2. **删 `memory/`**：跨 run 结论本来就在知识库 `Projects/WebNote/Project.md`；仓里留一份空索引只是维护成本。
3. **注册面整体退役**：删 `tools/doctor.py`、`tools/hooks/guard_write.py`、`.claude/agents/`、`.claude/settings.json` 以及对应测试；`bot.yaml` 只剩 `vendored:`。理由：它解决的是"多工具注册面互不兼容"，而实际只有一个工具在用，且写守卫依赖 CC 专有的 `agent_type` payload——换工具即失效。角色仍由 `agents/*.md` 的契约 + `AGENTS.md` 的"按路径读、自己扮演"规则承担。
4. **`tests/fixtures` + `test-web-archive.ps1` → `tests/manual/`**：需要真实浏览器的东西不该和 CI 违约测试混在一起。
5. **小红书链路移出**：`extract-xhs.py` / `run-xhs-note.py` / `skills/xhs-note` 打包到 `E:\Projects\archive\webnote-xhs-2026-11-09.tgz` 后删除；它与"网页笔记"主链无关，需要时另立一个 bot。
6. **四套"能不能跑"收敛为一套**：`check-env.py` + `.env.example` 定稿，`config/` 与 doctor 的 report 消失。
7. **`check-links.py` 从 `_migrations/` 升为 `tools/check-links.py`** 并进 CI。
8. **文档去重**：`README` 352 → 约 150 行、`README.en` 131 → 约 100 行，五步流程只在 `docs/architecture.md` 讲全。

**判据**（以后加东西前先问）：这份文件/脚本有没有一个真实的读者或执行者？没有就是设计债。机制只有在"换了工具就失效"的地方才值得写，其余靠约定与断言。

**代价**：少了"任意工具读 AGENTS.md 就自动获得角色注册与写入拦截"的能力；写边界退回提示词约束（`agents/verifier.md` 的 `writes/forbidden` + 降级声明）。若将来真的多工具并用，再把注册面按需加回来——它现在是 tarball 之外的一小段 YAML，重写成本很低。

## 2026-11-09 · 长期记忆回到 bot 目录 `memory/`（私有、不进 git）

**背景**：同一天早些时候刚把 `memory/` 删掉，理由是"索引 0 条、跨 run 结论本来就落知识库"。用户随后明确：记忆要跟着 bot 走，放在 `E:\Projects\bots\WebNote` 里。这两条并不矛盾——删掉的是一个**空壳索引**，现在建的是一个**有内容、且只在本机**的记忆。

**决定**：

1. `memory/MEMORY.md` 是长期记忆主体：定位与铁律、仍生效的判据、决策台账（含已被推翻的）、教训、沿革、未落地、本机事实、用户偏好。
2. `memory/log/<日期>.md` 是流水，只在追溯"当时为什么"时读；拿不准是否长期有效的先落这里，第二次出现再升级。
3. 整个 `memory/` 进 `.gitignore`：仓库公开，记忆里有本机路径与用户偏好，不适合上云。`test_memory_stays_private` 断言"被忽略 + 无被跟踪文件"。
4. 知识库 `Projects/WebNote/Project.md` 退回**指针**角色（它本来就写着 `state_authority: external_repo`），不再复制记忆内容。
5. 分工判据：**换一台机器还能不能用**——能用的进知识库，只对本机成立的留在这里。

**代价**：记忆随仓库走，别人 clone 不到（这是有意的）；换机器要手动搬 `memory/`，与 `AGENTS.md`、`persona/` 同类。

## 2026-11-09 · 旧的两份本机记忆归档（已被上一条修订：记忆回到 `memory/`）

**背景**：仓里还剩两处本机记忆：`.memory/_archive/`（2026-09-13 自称"已入库"，但库里只有 4 条 claim，且它写的库路径（旧库子目录）、项目名 `WebNote-Workflow`、Inbox 登记记录三样都已失效）与 `.workbuddy/memory/`（5 份会话日志 + 一份已实施的设计草案）。

**决定**：记忆的长期形态只有两种落点——**项目记忆**写知识库 `Projects/WebNote/Project.md`，**可迁移结论**写 claim。会话日志不进记忆库（那是流水账，会稀释检索命中）。据此把两处冻成一份 `## 历史沿革（2026-07 → 2026-09）` 段（三阶段 / 11 条决策台账带"现在是否还活着" / 4 条教训 / 2 项未落地），原始文件打包 `E:\Projects\archive\webnote-local-memory-2026-11-09.tgz` 后删除。

**判据**：归档要保留的是"当时为什么这么定"，以及"哪些已经被推翻"；后者比前者更值钱——没有它，后来的人会照着一份失效的决策继续做。

**配套**：`.gitignore` 只保留 `.workbuddy/`（工具会话会重建，属本机产物），去掉 `.memory/`；`AGENTS.md` 明确"跨 run 结论写知识库，仓内不要存第二份"。

## 2026-11-09 · 新 run 用 `runs/_template/` 空骨架，不动 `examples/`

**背景**：00–04 五个产物的表头一直靠 SKILL.md 的散文描述 + `examples/` 对照，实际开跑时是 AI 现编表头，列名与分区逐次漂移；`examples/` 又是三态改造前的冻结快照（故意不改），不能当格式基准。

**决定**：新增 `runs/_template/`（五份空骨架，进 git、只读）。`examples/` 保持原样继续冻结。两者分工：模板是空的格式契约，范例是跑完的真实教材。

**理由**：骨架文件比格式卡硬——AI 会直接复制，不需要先读懂规则；`examples/` 挪进 `runs/` 则会撞上 `runs/*` 的忽略规则，且本机已有同名运行目录。

**代价与配套**：
- `.gitignore` 需要 `!runs/_template/` 与 `!runs/_template/**` 两个例外（否则模板自己被忽略）。
- `bot.yaml` 里 verifier 的 `write_scope: runs/*/03-核查表.md` 会误匹配 `runs/_template/`，因此 `tools/hooks/guard_write.py` 显式拒绝任何 `runs/_template/` 写入。
- 三条测试兜底：模板文件齐全且表头与步骤卡一致、模板不被 gitignore、守卫拒绝写模板。
