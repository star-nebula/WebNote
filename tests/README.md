# tests · 验证层

`test_repo.py` 进 CI，本地改完结构或流程也要跑一遍。`manual/` 需要真实浏览器，不进 CI。

| 文件 | 验证什么 | 依赖 |
|---|---|---|
| `test_repo.py` | 只断言「改了会静默变坏」的六类事：① 技能入口与五个步骤文件齐全、frontmatter 可用、正文与文件名对得上 ② `AGENTS.md` 进 git、`AGENTS.local.md` 不进且不复述入口小节 ③ 被跟踪文件里没有私有路径、没有已退役的旧结构（`references/steps`、`agents/`、`_agent_scripts`） ④ `runs/_template/` 与各步骤的 `format_needles` 逐条一致、模板进 git ⑤ 外部技能副本真实、来源记在 `bot.yaml`、`SKILL.md` 指向的 references 都在 ⑥ 文档里写的路径真的存在、`README.md` 承诺的环境变量真的被代码读取 | pytest, pyyaml |
| `manual/test-web-archive.ps1` | `web-archive` 真机回归：钉钉、飞书、普通 HTML、登录墙、合并单元格、未知代码语言、Mermaid 源码、仅渲染图降级、连续无进展停止 | Windows PowerShell + Chromium 内核浏览器 |
| `manual/fixtures/*.html` | 上面 PS1 用的离线夹具，不联网、不写业务目录 | 无 |

```bash
python -m pytest tests -q                            # 不变量（跨平台，CI 同一套）
powershell -File tests/manual/test-web-archive.ps1   # 真机回归（Windows）
```

新增夹具放 `tests/manual/fixtures/`，命名 `<功能>-<场景>.html`。新增断言优先写结构不变量，别断言具体文案——也不要把「文件在不在」写成测试，git 已经是那个断言的来源。
