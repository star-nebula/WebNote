# tools/_migrations · 一次性维护脚本

这些是**已经跑过的一次性迁移 / 维护脚本**，保留作记录与回归参考。运行时工具在 `tools/`，测试在 `tests/`；本目录不参与任何运行时路径。

| 脚本 | 干什么 | 状态 |
|---|---|---|
| `check-links.py` | 检查全仓 Markdown 的相对链接是否指向真实文件；断链列「来源 → 链接」，退出码 1 | 长期可用，改完目录结构跑一次 |
| `rename-definition-files.py` | 把 `agents/`、`skills/webnote-workflow/references/steps/` 下的中文序号文件名改成英文名，并同步正文引用 | 已执行（2026-09-04） |
| `sanitize-example.py` | 脱敏 `examples/` 里的真实本地路径：路径抹掉、文件名保留；只处理 `examples/` | 每次从 `runs/` 复制新示例后跑 |
| `move-definitions-to-root.py` | 把 `agents/`、`steps/` 从 skill 内部移到项目根 | 已执行（2026-09-04），后被 2026-11-09 的结构调整反向覆盖 |
| `offline-workbuddy-web-archive.py` | 从 WorkBuddy 专家 / marketplace / 最近索引里移除旧的 `web-archive-expert`，保留插件目录以便回滚 | 已执行 |

## 用法

```bash
python tools/_migrations/check-links.py              # 全仓相对链接检查
python tools/_migrations/check-links.py --root .     # 指定项目根
python tools/_migrations/sanitize-example.py --dry-run
```

- 四个脚本都用 `Path(__file__).resolve().parent.parent.parent` 定位仓根；**本目录换位置要同步改这一行**。
- `rename-definition-files.py` 的重命名表 / 正文替换表内置：`01-归类师.md → classifier.md`、`02-笔记匠.md → distiller.md`、`03-核查官.md → verifier.md`、`00-采编*.md → collect*.md`、`04-确认.md → confirm.md`。再改名就改表重跑。
- `move-definitions-to-root.py` 只替换带 `skills/webnote-workflow/` 前缀的引用；裸引用需另加 `<项目根>/` 前缀。

> 历史状态：2026-09-04 把 `agents/` + `steps/` 移到项目根；2026-11-09 又把 `steps/` 收进 `skills/webnote-workflow/references/steps/`，让 SKILL.md 的「细则放 references/」约定成立。现以 `AGENTS.md` 与 `docs/architecture.md` 为准，脚本仅作记录。
