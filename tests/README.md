# tests · 验证层

`test_repo.py` 进 CI，本地改完结构或流程也要跑一遍。`manual/` 需要真实浏览器，不进 CI。

| 文件 | 验证什么 | 依赖 |
|---|---|---|
| `test_repo.py` | 只断言「改了会静默变坏」的四类事：① 契约文件齐全且 frontmatter 完整（4 个 SKILL.md / 5 张步骤卡 / 3 个角色）② `AGENTS.public.md` 与私有版一致 ③ 被跟踪文件里没有私有路径与身份泄漏 ④ `runs/_template/` 的表头与步骤卡一致、模板进 git 没被忽略 ⑤ 外部技能副本真实、来源可查、`SKILL.md` 指向的 references 都在 | pytest, pyyaml |
| `manual/test-web-archive.ps1` | `web-archive` 真机回归：钉钉、飞书、普通 HTML、登录墙、合并单元格、未知代码语言、Mermaid 源码、仅渲染图降级、连续无进展停止 | Windows PowerShell + Chromium 内核浏览器 |
| `manual/fixtures/*.html` | 上面 PS1 用的离线夹具，不联网、不写业务目录 | 无 |

```bash
python -m pytest tests -q                            # 不变量（跨平台，CI 同一套）
powershell -File tests/manual/test-web-archive.ps1   # 真机回归（Windows）
```

新增夹具放 `tests/manual/fixtures/`，命名 `<功能>-<场景>.html`。新增断言优先写结构不变量，别断言具体文案——也不要把「文件在不在」写成测试，git 已经是那个断言的来源。
