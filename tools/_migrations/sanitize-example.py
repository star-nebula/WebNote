#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""脱敏 examples/ 下的真实本地路径，避免开源时泄露用户名与目录结构。

把 `C:/Users/<用户名>/AppData/.../xxx.md` 这类绝对路径替换为 `<示例素材>/xxx.md`：
路径部分抹掉（会暴露用户名和目录习惯），文件名保留（说明文件类型，有参考价值）。

用法（先 dry-run 再实跑）：
    python _agent_scripts/sanitize-example.py --dry-run
    python _agent_scripts/sanitize-example.py

**每次从 runs/ 复制新示例到 examples/ 之后，都要跑一次。**

注意：只处理 examples/ 目录。runs/ 里的原始记录保持原样（不进 git，无需脱敏）。
"""

import argparse
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent.parent
EXAMPLES = ROOT / "examples"

# 绝对路径：盘符 + 至少一级目录 + 文件名
# lookbehind 排除 https:// 之类（前面的字母会被 (?<![A-Za-z0-9]) 挡掉）
ABS_PATH = re.compile(r"(?<![A-Za-z0-9:/\\])([A-Za-z]:[/\\])(?:[^/\\|`\s\"']+[/\\])+([^/\\|`\s\"']+)")

PLACEHOLDER = "<示例素材>/"


def sanitize(text):
    return ABS_PATH.sub(lambda m: PLACEHOLDER + m.group(2), text)


def main():
    parser = argparse.ArgumentParser(description="脱敏 examples/ 下的本地路径")
    parser.add_argument("--dry-run", action="store_true", help="只报告，不写入")
    args = parser.parse_args()

    if not EXAMPLES.exists():
        print(f"没有 examples/ 目录：{EXAMPLES}")
        return 1

    total = 0
    for md in sorted(EXAMPLES.rglob("*.md")):
        original = md.read_text(encoding="utf-8")
        cleaned = sanitize(original)
        if cleaned == original:
            continue
        hits = len(ABS_PATH.findall(original))
        total += hits
        print(f"{md.relative_to(ROOT)}  ({hits} 处)")
        for m in ABS_PATH.finditer(original):
            print(f"    {m.group(0)}")
            print(f"      → {PLACEHOLDER}{m.group(2)}")
        if not args.dry_run:
            md.write_text(cleaned, encoding="utf-8")

    print(f"\n共 {total} 处。")
    # 自检：确认没有 URL 被误伤
    leftover = []
    for md in EXAMPLES.rglob("*.md"):
        for i, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
            if "https://" in line and "<示例素材>" in line:
                leftover.append((md.relative_to(ROOT), i))
    if leftover:
        print("警告：以下行的 URL 可能被误改，请人工确认：")
        for src, lineno in leftover:
            print(f"  {src}:{lineno}")
        return 1
    print("URL 未被误伤。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
