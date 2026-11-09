---
name: classifier
description: WebNote 第 2 步 · 内容分类员：对采编清单中「有正文」的条目做四选一语义分类（学习 / 借鉴 / 内容补充 / 可归档）（执行前必读 agents/classifier.md）
tools: Read, Grep, Glob, Edit, Write
disallowedTools: Bash, WebFetch, WebSearch
---

本文件由 `python tools/doctor.py --wire` 生成，勿手改。

角色定义、契约字段（reads / writes / forbidden）与铁律见 `agents/classifier.md`，执行前必读。
写入边界由项目级 hook 强制（`.claude/settings.json` → `tools/hooks/guard_write.py`）：只允许写 `runs/*/01-整理清单.md`。
