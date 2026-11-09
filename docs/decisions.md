# 项目决策记录

> 从 SemanticMemory 迁入（2026-10-31）。原 claim 已归档，`--include-history` 仍可查。

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
