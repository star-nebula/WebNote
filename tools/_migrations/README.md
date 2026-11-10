# tools/_migrations · 一次性维护脚本

这些是**已经跑过的一次性迁移 / 维护脚本**，保留作记录与回归参考。运行时工具在 `tools/`，测试在 `tests/`；本目录不参与任何运行时路径。

| 脚本 | 干什么 | 状态 |
|---|---|---|
| `rename-definition-files.py` | 把 `agents/`、`skills/webnote-workflow/references/steps/` 下的中文序号文件名改成英文名，并同步正文引用 | 已执行（2026-09-04） |
| `sanitize-example.py` | 脱敏 `examples/` 里的真实本地路径；目录已归档为 `docs/history/`，脚本留着备查 | 已过期（目标目录不存在） |
| `move-definitions-to-root.py` | 把 `agents/`、`steps/` 从 skill 内部移到项目根 | 已执行（2026-09-04），后被 2026-11-09 的结构调整反向覆盖 |
| `offline-workbuddy-web-archive.py` | 从 WorkBuddy 专家 / marketplace / 最近索引里移除旧的 `web-archive-expert`，保留插件目录以便回滚 | 已执行 |

`check-links.py` 已升级为常用工具，移到了 `tools/check-links.py`（进 CI）；这里不再保留副本。

## 用法

```bash
python tools/_migrations/sanitize-example.py --dry-run
python tools/_migrations/rename-definition-files.py --dry-run   # 改了名字表再跑前先看 diff
```

- 本目录脚本用 `Path(__file__).resolve().parent.parent.parent` 定位仓根；**换位置要同步改这一行**。
- `rename-definition-files.py` 的重命名表 / 正文替换表内置：`01-归类师.md → classifier.md`、`02-笔记匠.md → distiller.md`、`03-核查官.md → verifier.md`、`00-采编*.md → collect*.md`、`04-确认.md → confirm.md`。
- `move-definitions-to-root.py` 只替换带 `skills/webnote-workflow/` 前缀的引用；裸引用需另加 `<项目根>/` 前缀。

> 历史状态：2026-09-04 把 `agents/` + `steps/` 移到项目根 → 2026-11-09 收进 `skills/webnote-workflow/references/steps/` → 2026-11-10 五步合一，改成 `skills/webnote-workflow/steps/`（`references/steps/` 与 `agents/` 已不存在）。现以 `AGENTS.md` 与 `docs/architecture.md` 为准，脚本仅作记录。
