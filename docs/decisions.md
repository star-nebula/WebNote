# 项目决策记录

> 从 SemanticMemory 迁入（2026-10-31）。原 claim 已归档，`--include-history` 仍可查。

## 记忆分层：核心记忆进 AGENTS.md，长期记忆进 memory/

**问题**：`persona/SOUL.md` 与 `AGENTS.md` 内容重叠（身份、专职角色、硬约束、汇报格式各写一遍），且 SOUL 里的落库路径还是错的（`<知识库根>/vault/Resources/`（`vault/` 早已不存在））。同时没有任何地方沉淀"跨 run 的经验"——都散在 `runs/`（过程）和知识库（产出）里。

**决定**：

1. **核心记忆不单独建文件**，写进 `AGENTS.md` 的「核心记忆」小节（私有块内）。理由：它必须常驻上下文，多一个文件就多一次读取、多一个漂移点，而 `AGENTS.md` 本来就是被自动加载的那一份。`persona/SOUL.md` 内容并入后删除（原稿在归档包 `webnote-role-2026-11-09.tgz`）。
2. **长期记忆独立成 `memory/`**：`index.md` 一行一条做检索，`long-term/` 一条一文件（frontmatter 标 `date/topic/confidence/source`）。理由：记忆要按需取，整目录塞进上下文只会稀释注意力；一条一文件也让"索引腐烂"可被测试发现。
3. **角色与技能不做合并**：`agents/` 与 `skills/` 的位置是被工具机制钉住的（`skills/<name>/SKILL.md` 是发现约定，`AGENTS.md` 是入口文件名），搬家即失去自动发现。只有长期记忆没有任何约定，才需要人为给它一个目录。
4. 边界：`runs/` 是过程不是记忆；记忆只从 `03-核查表.md` 这类已核实的产物里提炼，且落盘要用户点头。角色（subagent）不得写记忆。

**代价**：多一层目录与一条索引维护成本；换来"下次怎么做得对"有确定落点，且不用把整份历史塞进上下文。

## 角色分发：真源 + 生成物，写入边界挂在项目级 hook

**问题**：同一个角色定义要同时喂给多种 agent 工具，而各工具的注册面互不兼容；手写多份薄壳后，`description` 会漂移，且薄壳里写的 `permissions.allow/deny` 在 Claude Code 里根本不是可用字段（实测 CC 2.1.310 只解析 `name/description/prompt/tools/disallowedTools/model/effort/permissionMode/mcpServers/hooks/maxTurns/...`），"核查官只能写 03-核查表.md" 因此毫无机制保障。

**决定**：

1. 角色定义只有一处 —— `agents/<name>.md`（含 `description` 与 `context/reads/writes/forbidden` 契约），平台无关。
2. 注册信息只有一处 —— `bot.yaml`（`tools` / `disallowed_tools` / `write_scope` / `fresh_context`）。
3. `.claude/agents/*.md` 与 `.claude/settings.json` 是**生成物**，由 `tools/doctor.py --wire` 产出，CI 用 `--check` 打回手改。
4. 写入边界不依赖 agent frontmatter 的 `hooks`（实测不执行），改挂项目级 `PreToolUse`：`tools/hooks/guard_write.py` 读 payload 里的 `agent_type`，按 `bot.yaml` 的 `write_scope` 判定，越界 exit 2。

**代价/收益**：多一个生成步骤与一条 CI 断言；换来一份定义喂所有工具，且"越界写入"从提示词约束变成机制拦截（实测 verifier 写 `runs/x/02-笔记.md` 被拒、`runs/x/03-核查表.md` 放行）。

## WebNote 架构决策：5 Agent 精简为主会话 + 3 subagent

不是每一步都需要独立的 AI 上下文。 确定性的事主会话自己干，只有真正需要独立判断的才创建 subagent：

- 原 claim：`decision-2b28f2c3553f`（已归档）
- 来源：`.backup/Memory-20261029/Decisions/WebNote架构决策-5Agent精简为主会话+3subagent.md`

## 网页知识提取核心能力直写 Obsidian

网页来源正文直接写入 Resources 对应来源目录，生成的知识笔记写入 Knowledge 对应域并关联 MOC。正常采集、提炼和落库不再逐条提案；内容必须来自实际页面或媒体，记录 URL、来源类型和限制。

- 原 claim：`rule-webnote-direct-write`（已归档）
- 来源：`.backup/Memory-20261029/Preferences/网页知识提取机器人-核心能力直写Obsidian.md`

## 2026-11-09 · 新 run 用 `runs/_template/` 空骨架，不动 `examples/`

**背景**：00–04 五个产物的表头一直靠 SKILL.md 的散文描述 + `examples/` 对照，实际开跑时是 AI 现编表头，列名与分区逐次漂移；`examples/` 又是三态改造前的冻结快照（故意不改），不能当格式基准。

**决定**：新增 `runs/_template/`（五份空骨架，进 git、只读）。`examples/` 保持原样继续冻结。两者分工：模板是空的格式契约，范例是跑完的真实教材。

**理由**：骨架文件比格式卡硬——AI 会直接复制，不需要先读懂规则；`examples/` 挪进 `runs/` 则会撞上 `runs/*` 的忽略规则，且本机已有同名运行目录。

**代价与配套**：
- `.gitignore` 需要 `!runs/_template/` 与 `!runs/_template/**` 两个例外（否则模板自己被忽略）。
- `bot.yaml` 里 verifier 的 `write_scope: runs/*/03-核查表.md` 会误匹配 `runs/_template/`，因此 `tools/hooks/guard_write.py` 显式拒绝任何 `runs/_template/` 写入。
- 三条测试兜底：模板文件齐全且表头与步骤卡一致、模板不被 gitignore、守卫拒绝写模板。
