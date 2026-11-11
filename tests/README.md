# tests · 验证层

分两层：**断言仓库不变量**（进 CI）与**真机回归**（要浏览器，不进 CI）。
另外有一个被生产线调用的校验器——它不在 tests 里，在 `tools/validate_run.py`。

| 文件 | 验证什么 | 依赖 |
|---|---|---|
| `test_repo.py` | 仓库不变量：技能入口与五个步骤文件齐全、`AGENTS.md` 进 git 而 `AGENTS.local.md` 不进、无私有路径与已退役结构、`runs/_template/` 与各步骤的 `format_needles` 一致、外部技能副本真实、文档里的路径与环境变量真的成立 | pytest, pyyaml |
| `test_validate_run.py` | **校验器本身**：一份干净 run 必须通过，然后逐类注入真错（条数漂移、断号、把 OCR 标成直接引用、缺出处、提案漏条目/重复/缺页、统计不符）必须被指出来；并断言它真的被 `AGENTS.md`、`pre-push`、`03-confirm.md` 调用 | pytest |
| `test_naming.py` | 落库命名三档升级、大小写撞名、非法字符、佚名、空标题 | pytest |
| `test_safe_path.py` | 跨盘不崩、分隔符统一，且生产工具不许再抄一份实现 | pytest |
| `test_extract_document.py` | 提取工具的成功路径（自己造的最小 PDF，不联网、不要 key）与失败契约 | pytest, pypdf |
| `manual/test-web-archive.ps1` | `web-archive` 真机回归：钉钉、飞书、普通 HTML、登录墙、合并单元格、Mermaid、仅渲染图降级 | Windows PowerShell + Chromium |
| `manual/fixtures/*.html` | 上面 PS1 用的离线夹具 | 无 |

```bash
python -m pytest tests -q                       # 全部（CI 同一套）
python tools/validate_run.py --all              # 手上的 run 是否自洽（pre-push 也会跑）
powershell -File tests/manual/test-web-archive.ps1   # 真机回归（Windows）
```

新增夹具放 `tests/manual/fixtures/`。写断言的口径：

- 优先断言**结构**（能消费、能对齐、能复算），别断言文案
- 别把「文件在不在」写成测试——git 已经是那个断言的来源
- 一个新断言如果不写，会静默坏成什么样？说不出来就别写
