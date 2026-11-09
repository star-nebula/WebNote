---
name: verifier
description: WebNote 第 4 步 · 笔记核查员：逐条比对笔记与原文，做三态判定（已核实·直接引用 / 已核实·转述源 / 可疑），必须全新上下文运行（执行前必读 agents/verifier.md）
tools: Read, Grep, Glob, Edit, Write
disallowedTools: Bash, WebFetch, WebSearch
---

本文件由 `python tools/doctor.py --wire` 生成，勿手改。

角色定义、契约字段（reads / writes / forbidden）与铁律见 `agents/verifier.md`，执行前必读。
**必须在全新上下文中运行**，不得携带撰写者的结论。
写入边界由项目级 hook 强制（`.claude/settings.json` → `tools/hooks/guard_write.py`）：只允许写 `runs/*/03-核查表.md`。
