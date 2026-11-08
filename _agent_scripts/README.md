# _agent_scripts

本目录存放**项目维护用的辅助脚本**，供 agent 调用，不参与工作流运行（工作流用的工具在 `tools/`）。

## check-links.py

检查项目内所有 Markdown 文件的**相对链接**是否指向真实文件。

```bash
python _agent_scripts/check-links.py
python _agent_scripts/check-links.py --root <项目根>
```

- 链接按「相对于该 md 文件所在目录」解析，与 Markdown 语义一致
- 自动跳过外链、`mailto:`、纯锚点
- 自动 URL 解码（`%20` → 空格），以匹配带空格的文件名
- 发现断链时列出「来源文件 → 断掉的链接」，退出码 1；全部有效则退出码 0

**何时用**：新增或移动文件后、发布前、重构目录结构后。开源项目里断链是硬伤，改完目录结构务必跑一次。

## rename-definition-files.py

把 `agents/` 与 `steps/` 下的定义文件改名为英文名（去掉序号），并同步更新全项目引用。

```bash
python _agent_scripts/rename-definition-files.py --dry-run   # 先看会改什么
python _agent_scripts/rename-definition-files.py             # 实跑
```

- 内置重命名表 + 正文替换表（含 frontmatter 里的 `name:` 与 `must_not_share_context_with`）
- 替换项按长度降序，避免子串误伤；跳过 `.git/` 与 `runs/`（历史档案保持原貌）
- 跑完自动做残留检查，列出仍需人工确认的引用

**已执行过一次**（2026-09-04）：`01-归类师.md` → `classifier.md`，`02-笔记匠.md` → `distiller.md`，
`03-核查官.md` → `verifier.md`，`00-采编*.md` → `collect*.md`，`04-确认.md` → `confirm.md`。
脚本本身保留作为记录；若再改名，直接改脚本里的两张表重跑即可。

## sanitize-example.py

脱敏 `examples/` 下的真实本地路径，避免开源时泄露用户名与目录结构。

```bash
python _agent_scripts/sanitize-example.py --dry-run
python _agent_scripts/sanitize-example.py
```

- 把 `C:/Users/<用户名>/AppData/.../xxx.md` 替换为 `<示例素材>/xxx.md`——**路径抹掉，文件名保留**（文件名说明文件类型，有参考价值）
- 用 lookbehind 排除 `https://` 之类，避免误伤 URL；跑完自检并报告
- 只处理 `examples/`；`runs/` 里的原始记录不改（不进 git）

**何时用**：**每次从 `runs/` 复制新示例到 `examples/` 之后都要跑一次。**

## move-definitions-to-root.py

把 `agents/` 与 `steps/` 从 `skills/webnote-workflow/` 移到项目根，并同步全项目引用路径。

```bash
python _agent_scripts/move-definitions-to-root.py --dry-run
python _agent_scripts/move-definitions-to-root.py
```

- 角色定义与操作卡是**流程资产**，不属于某个 skill 的私有实现；移到项目根后与各工具注册位语义对齐
- 全局替换 `skills/webnote-workflow/agents|steps/` 前缀 → 项目根相对路径
- 跳过 `.git/`、`runs/`、`__pycache__`、`node_modules`；跑完自动做残留检查

**已执行过一次**（2026-09-04）：agents/ + steps/ 已移到项目根。此后**不要再把这两个目录放回 skill 里**。
注意：本脚本只替换带 `skills/webnote-workflow/` 前缀的引用；SKILL.md 里的裸引用需另加 `<项目根>/` 前缀（已手动完成）。

## web-archive-smoke.html

`web-archive` 迁移与回归用的本地夹具，覆盖标题、段落、引用、围栏代码块和行内加粗。它不访问网络，也不会写入业务目录。

使用方式：以 CDP 调试模式启动 Chrome/Edge，打开该文件的 `file:///` URL，再依次调用 `skills/web-archive/scripts/` 下的 `harvest.ps1`、`merge-blocks.ps1`、`render-md.ps1`。输出应保留阅读顺序、引用、代码语言与行内样式。

---

> 注意：以上脚本均位于 `<项目根>/_agent_scripts/`，项目根为脚本所在目录的上级。若移动了本目录，需同步修改脚本里的上溯级数。
