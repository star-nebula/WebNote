#!/usr/bin/env python3
"""
落库文件的命名规则（本仓唯一实现）。

规则只有一条主链，写在 skills/webnote-workflow/steps/03-confirm.md：
  1. 默认**直接用原标题**
  2. 只有同名已存在时，才追加 ` - <作者> - <平台>`
  3. 仍同名，再加 ` - <YYYY-MM-DD>`
  4. 覆盖永远不许；同名不停下来问，按序自动升级

工具只负责算名字，不负责写文件、不负责判断该往哪个目录放——
目录由使用者的 AGENTS.local.md 决定。

用法：
  python tools/naming.py "原标题"
  python tools/naming.py "原标题" --author 张三 --platform 公众号 --taken "原标题.md"
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import unicodedata
from pathlib import Path

# Windows / POSIX 都不安全的字符，加控制字符
ILLEGAL = '<>:"/\\|?*'
FALLBACK_AUTHOR = "佚名"
MAX_STEM = 120  # 只是为了不撞 Windows 260 字符路径上限；正常标题远小于此


def sanitize(text: str) -> str:
    """把一段文字变成可以出现在文件名里的片段。"""
    text = unicodedata.normalize("NFC", str(text)).strip()
    text = "".join(ch for ch in text if ch not in ILLEGAL and ord(ch) >= 32)
    text = re.sub(r"\s+", " ", text)
    text = text.rstrip(" .")  # Windows 不允许以点或空格结尾
    return text[:MAX_STEM].rstrip(" .")


def _key(name: str) -> str:
    return name.casefold()


def landing_name(
    title: str,
    author: str | None = None,
    platform: str | None = None,
    taken: set[str] | frozenset[str] = frozenset(),
    suffix: str = ".md",
    today: str | None = None,
) -> str:
    """按三档升级算出一个不与 taken 冲突的文件名（不含目录）。"""
    base = sanitize(title) or "未命名"
    used = {_key(n) for n in taken}
    author = sanitize(author) if author else ""
    platform = sanitize(platform) if platform else ""

    candidates = [base]
    parts = []
    if author:
        parts.append(author)
    elif platform:
        parts.append(FALLBACK_AUTHOR)
    if platform:
        parts.append(platform)
    middle = " - ".join(parts)
    if middle:
        candidates.append(f"{base} - {middle}")
    date = today or dt.date.today().isoformat()
    if middle:
        candidates.append(f"{base} - {middle} - {date}")
    else:
        candidates.append(f"{base} - {date}")

    for cand in candidates:
        if _key(cand + suffix) not in used:
            return cand + suffix
    # 理论上到不了这里（日期档几乎唯一），但同一天同标题重复采写会撞：
    n = 2
    while _key(f"{candidates[-1]} ({n}){suffix}") in used:
        n += 1
    return f"{candidates[-1]} ({n})" + suffix


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="按三档升级算出落库文件名")
    ap.add_argument("title", help="原标题")
    ap.add_argument("--author", help="作者；缺省时第二档写「佚名」")
    ap.add_argument("--platform", help="平台；没有就省略这一段")
    ap.add_argument("--taken", nargs="*", default=[], help="目标目录里已存在的文件名")
    ap.add_argument("--today", help="第 3 档的日期，默认今天（YYYY-MM-DD）")
    ap.add_argument("--dir", help="目标目录；给了就直接扫目录里已存在的文件")
    args = ap.parse_args(argv)

    taken = set(args.taken)
    if args.dir:
        d = Path(args.dir)
        if d.is_dir():
            taken |= {p.name for p in d.iterdir()}

    name = landing_name(args.title, args.author, args.platform, taken, today=args.today)
    print(json.dumps({"name": name, "title": args.title}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
