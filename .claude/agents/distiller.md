---
name: distiller
description: WebNote 第 3 步 · 笔记提炼员：对整理清单中「有正文」的页面提取每页 3~5 条核心要点，每条标注出处与来源类型（执行前必读 agents/distiller.md）
tools: Read, Grep, Glob, Edit, Write
disallowedTools: Bash, WebFetch, WebSearch
---

本文件由 `python tools/doctor.py --wire` 生成，勿手改。

角色定义、契约字段（reads / writes / forbidden）与铁律见 `agents/distiller.md`，执行前必读。
写入边界由项目级 hook 强制（`.claude/settings.json` → `tools/hooks/guard_write.py`）：只允许写 `runs/*/02-笔记.md`。
