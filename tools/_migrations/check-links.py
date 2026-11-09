#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查项目内 Markdown 文件的相对链接与 SKILL.md 契约字段引用是否都指向真实文件。

用法：
    python _agent_scripts/check-links.py
    python _agent_scripts/check-links.py --root <项目根>

只检查 Markdown 链接 [x](path)，跳过外链、锚点和 mailto。
"""

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import unquote

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
SKIP_SCHEMES = ("http://", "https://", "mailto:", "#", "data:")


def extract_links(text):
    out = []
    for raw in LINK_RE.findall(text):
        raw = raw.strip()
        if raw.startswith(SKIP_SCHEMES):
            continue
        path = unquote(raw.split("#")[0].strip())
        if not path:
            continue
        out.append(path)
    return out


def main():
    parser = argparse.ArgumentParser(description="检查项目内相对链接是否有效")
    parser.add_argument("--root", default=None, help="项目根目录，默认取本文件的上级的上级")
    args = parser.parse_args()

    # 本脚本位于 <项目根>/_agent_scripts/，故上溯两级
    root = Path(args.root) if args.root else Path(__file__).resolve().parent.parent.parent
    root = root.resolve()

    # 跳过私有记忆目录（不属于开源发布内容，且内部文件名引用随时会过时）
    SKIP_DIRS = {".git", "__pycache__", ".workbuddy", ".memory", "runs", ".claude", ".github", "node_modules", "site-packages"}
    md_files = sorted(
        p for p in root.rglob("*.md")
        if not (SKIP_DIRS & set(p.parts)) and not any(part.startswith(".venv") for part in p.parts)
    )

    broken, checked = [], 0
    for md in md_files:
        # 链接按「相对于该 md 文件所在目录」解析
        for link in extract_links(md.read_text(encoding="utf-8", errors="replace")):
            target = (md.parent / link).resolve()
            checked += 1
            if not target.exists():
                broken.append((md.relative_to(root), link, target.relative_to(root)
                               if target.is_relative_to(root) else target))

    print(f"项目根：{root}")
    print(f"扫描 {len(md_files)} 个 Markdown 文件，检查 {checked} 条相对链接\n")

    if broken:
        print(f"发现 {len(broken)} 条断链：\n")
        for src, link, _ in broken:
            print(f"  {src}")
            print(f"      → {link}")
        return 1

    print("全部链接有效。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
