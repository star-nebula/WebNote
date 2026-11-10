# 项目决策记录

> 从 SemanticMemory 迁入（2026-10-31）。原 claim 已归档，`--include-history` 仍可查。

## 外部技能：副本进仓、真源记在 bot.yaml，exe 版本号不算真源

**问题**：`browser-skill` 来自腾讯的 `Tencent/BrowserSkill`（MIT），既不由本仓维护，也不是技能库维护的——技能库那份是 2026-09-30 从 bsk 产物人工搬进去的快照。链条是三跳：上游仓库 → `crates/bsk-cli/skill/` → 技能库 → 本仓 `skills/browser-skill/`，最后一跳当时用 `.skillshare` 的 `mode: copy` 镜像。

**发现**：查上游时发现我们落后一代。上游 2026-11 起把单文件 `SKILL.md`（229 行 / 11,406 B）改成「主体 131 行 + `references/` 13 个文件 / 81 KB」，上游 `crates/bsk-cli/src/skill_install/` 里的 `legacy-digests.txt`、`provenance.rs`、`sync.rs` 就是这次布局迁移的痕迹。

**决定**：

1. **真源写进 `bot.yaml` 的 `vendored:` 段**（`upstream` / `subdir` / `ref`（完整 commit sha）/ `snapshot` / `layout` / `files`），因为本地镜像配置只描述「从哪里 copy」，说不清「上游是哪一代」。
2. **不用 `bsk --version` 当基准**：别人机器上不一定有那个 exe，而且 exe 与仓库本来就可能不同代。
3. **检查分两层**：`tools/check_vendor.py`（离线：副本存在、是真目录不是链接、文件数与 `bot.yaml` 一致；进 CI）与 `--online`（按记录的 ref 拉上游 tree API 逐个比 blob sha，并报上游 HEAD 是否前进；联网、可能限流，不进 CI）。
4. **副本按上游布局整体覆盖**，不只换 `SKILL.md`——主体里引用了每个 references 文件，只同步一半会让 agent 读到悬空引用（`test_vendored_references_all_reachable` 守着这条）。
5. ~~**库那一跳保留**：skillshare 的 `include` 按 `<name>/SKILL.md` 找技能，上游是 `crates/bsk-cli/skill/SKILL.md`（目录名 `skill`），直连需要先改名，比中转更绕。同步时两份一起换，否则下次 `skillshare sync -p` 会把副本退回旧版。~~ **已推翻（2026-11-10）**，见下。

**代价**：仓库多 88 KB 与 13 个文件；`--online` / `--pull` 依赖 `gh` 或 `GITHUB_TOKEN`（匿名 API 会 403 限流）。

**修订（2026-11-10）：删掉 `.skillshare/`，改上游直取**

上面第 5 条把「本地中转」当成了省事，实际反了：

- 中转那一跳（技能库 `E:\Agent\skills\browser-skill`）既不是本仓维护，也不是上游维护，却是链上唯一「谁都没责任更新」的一环；
- 它把真源方向倒置了——`skillshare sync -p` 是从库往仓复制，库没更新时跑一次就静默回退（`docs/README.md` 当时自己就写着这句警告）；
- 维护成本落在人身上：升版必须两份一起换，漏一份等于白做。

现在只有两跳：上游 `Tencent/BrowserSkill` → 本仓 `skills/browser-skill/`。`check_vendor.py --pull` 拉上游 HEAD 的 tree、按 blob sha 下载原始字节整体覆盖、删掉上游已没有的文件，并把 `ref` / `snapshot` / `files` 写回 `bot.yaml`。`--online` 改为对照**记录的代际**，因此它同时回答两个问题：副本有没有被手改、上游有没有前进。

测试相应改为断言「副本是真目录、无链接、`.skillshare` 不许回来、文件数与 `bot.yaml` 一致」。代价：升版需要 `gh` 登录或 `GITHUB_TOKEN`；不再有本地离线镜像源。

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

## 2026-11-10 · 五步合一：流水线定义只留一份

**问题**：同一个五步流程被写在四个地方——`docs/architecture.md` 的顺序表、`skills/webnote-workflow/SKILL.md` 的派发表、`references/steps/` 的五张卡、`agents/` 的三份角色定义，外加 `runs/_template/` 的表头。审计实测：改一步的上下文要求要动 3 处（其中 2 处会漏，`AGENTS.md:24-25` 的独立上下文表就与 `agents/*.md` 的 `context: isolated` 相反）；加一步要动 9 处。`references/steps/` 还自称"五步"却只有采编与确认，角色在隔壁——"五步"这个概念本身没有对应物。

**决定**：`skills/webnote-workflow/steps/` 是流水线的唯一定义处。

1. `00-collect.md` / `01-classify.md` / `02-distil.md` / `03-verify.md` / `04-confirm.md`，**序号由文件名表达**，不另设顺序表；采编分支卡收进 `steps/branches/`。
2. 角色属性进步骤文件 frontmatter（`context` / `reads` / `writes` / `forbidden` / `produces` / `format_needles`）。`agents/` 目录删除——它的三个文件本来就是这三个步骤本身。
3. 产出格式针（表头、必备小节）写进对应步骤文件的 `format_needles`，`tests/test_repo.py` 从它派生比对 `runs/_template/`。**规范成了测试的输入，而不是测试的旁注。**
4. 铁律只在 `docs/architecture.md` 定义一处，`AGENTS.md` 与 `SKILL.md` 只留指针，并由测试拦住废弃版本回流。

**为什么不是别的方案**：
- 「加一份 `pipeline/00-05.yaml` 顺序表」会新增第五份副本，还是要人同步——维护成本不降反升。
- 「保留 `agents/` 只删 `references/steps/`」仍需两处改 `context`，且 `steps/` 无法说清"每步谁执行"。
- 「角色与步骤拆成 `roles/` + `steps/`」是当前四处的等价重排，只是换了名字。

**代价**：
- 步骤文件同时是"给调度器读的操作卡"和"给 subagent 读的角色契约"。两份读者读同一个文件——但这是有意的：subagent 本来就需要知道调度器会给它什么、它必须交回什么。
- 序号是文件名的一部分，重排步骤要改名（5 个文件），换来的是一条人人可读的顺序。
- 分支卡与主步骤同在 `steps/` 下，靠 `branches/` 子目录分隔。

**维护成本对照**：改一步的上下文 3 处 → **1 处**；改产出格式 4 处 → **2 处**（步骤文件 + 模板，测试自动跟随）；加一步 9 处 → **3 处**（新步骤文件、模板、README 目录树——后两项有测试兜底）。

## 2026-11-10 · 删 `memory/`：错误驱动的改进要落在会失败的东西上

**背景**：`memory/` 是我在 11-09 建的私有记忆目录（`MEMORY.md` 102 行 + `log/`）。用户问它到底有没有必要，并说明初衷：**把运行出错的问题记下来，之后据此改进流程**。

**实测**：
- 102 行里 75 行是 `docs/decisions.md`、`docs/architecture.md`、vault `Projects/WebNote/Project.md` 已有的内容；只有「本机事实」8 条 +「用户偏好」5 条是它独有的。
- `log/` 两份文件全是「我改了什么」（搬记忆、清减 1,400 行），而 `git log --stat` 记得更准、还带 diff。
- **没有一条运行故障记录**。唯一的故障线索是「未落地」里的 `extract-image-ocr.py` 跨盘符崩溃——写进私有记忆一年也不会被修，因为没有触发点。
- 已发生漂移：它的五步表写着 `.../steps/confirm.md`、`agents/classifier.md`，这些路径早已不存在。任何第三份台账都会这样。

**决定**：

1. 删 `memory/` 目录（原始文件归档 `E:\Projects\archive\webnote-memory-2026-11-10.tgz`）。私有事实（本机路径、偏好）并进 `AGENTS.md` 的私有块——它本来就被自动加载，比一个要人记得读的文件更强。
2. 运行异常写进**当次运行**的产物：`runs/<run>/00-采编清单.md` 新增「运行异常」节（`format_needles` 已登记，模板同步）。理由：异常发生在那次运行里，读者是下一次的调度器，就近才写得上。
3. **升级出口**：同一异常第二次出现，必须变成一条测试（首选，红了就非修不可）或本文档的一条。第三条路——继续堆在列表里——不算改进。

**为什么不是「把 memory 维护得更好」**：改进只在你改了一个**会失败的东西**时发生。记忆文件不在其中，它没有读者、没有 diff、没有红绿。

**代价**：没有跨会话的私有记忆文件了；换机器搬 `AGENTS.md` 私有块即可（比搬一个目录更简单）。原先记在 `memory/` 的决策台账、判据、沿革都在本文档、`architecture.md` 与 vault 里，没有丢失。

## 已知缺陷（接管原 `memory/` 的「未落地」）

- `tools/extract-image-ocr.py` 在 Windows 跨盘符（`C:` ↔ `E:`）时 `os.path.relpath` 抛 `ValueError`；规避方式写在 `steps/branches/image.md`，**代码未修**。
- 三态规范缺一份"标准示范"范例；现有 `docs/history/` 是两态时代的存档，`runs/_template/` 是空骨架。有真实多媒体批次时补。
- `README.en.md` 与 `README.md` 的内容对等性没有断言，靠人维护。
