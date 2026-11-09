# 项目决策记录

> 从 SemanticMemory 迁入（2026-10-31）。原 claim 已归档，`--include-history` 仍可查。

## WebNote 架构决策：5 Agent 精简为主会话 + 3 subagent

不是每一步都需要独立的 AI 上下文。 确定性的事主会话自己干，只有真正需要独立判断的才创建 subagent：

- 原 claim：`decision-2b28f2c3553f`（已归档）
- 来源：`.backup/Memory-20261029/Decisions/WebNote架构决策-5Agent精简为主会话+3subagent.md`

## 网页知识提取核心能力直写 Obsidian

网页来源正文直接写入 Resources 对应来源目录，生成的知识笔记写入 Knowledge 对应域并关联 MOC。正常采集、提炼和落库不再逐条提案；内容必须来自实际页面或媒体，记录 URL、来源类型和限制。

- 原 claim：`rule-webnote-direct-write`（已归档）
- 来源：`.backup/Memory-20261029/Preferences/网页知识提取机器人-核心能力直写Obsidian.md`
