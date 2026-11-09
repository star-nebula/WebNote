# tests · 验证层

CI（`.github/workflows/ci.yml`）跑同一套；本地改完结构或流程后也跑一遍。

| 文件 | 验证什么 | 依赖 |
|---|---|---|
| `test_repo.py` | 仓库不变量：五个技能各有带 frontmatter 的 `SKILL.md`、五张步骤卡齐全、三个角色定义带 `context` 契约、被跟踪文件里没有私有路径/身份泄漏、私有 `AGENTS.md` 与 `persona/` 没进 git、无旧路径残留、`AGENTS.public.md` 与私有版一致 | pytest |
| `test-web-archive.ps1` | `web-archive` 真机回归：钉钉、飞书、普通 HTML、登录墙、合并单元格、未知代码语言、Mermaid 源码、仅渲染图降级、连续无进展停止 | Windows PowerShell + Chromium 内核浏览器 |
| `fixtures/*.html` | 上面 PS1 用的离线夹具，不联网、不写业务目录 | 无 |

```bash
python -m pytest tests -q                     # 不变量（跨平台）
powershell -File tests/test-web-archive.ps1   # 真机回归（Windows）
```

新增夹具放 `tests/fixtures/`，命名 `<功能>-<场景>.html`；新增断言优先写"结构不变量"，而不是断言具体文案。
