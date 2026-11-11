#!/usr/bin/env python3
"""
路径小工具：跨盘的相对路径。

`os.path.relpath` 在 Windows 上遇到不同盘符会抛 `ValueError`——
这是 2026-11 真踩到过的崩溃（图片在 D 盘、工作目录在 E 盘）。
本仓所有需要"给人看的相对路径"的地方都走这里，不要各自 try/except。
"""

from __future__ import annotations

import os


def safe_relpath(path: str, base: str | None = None) -> str:
    """同盘给相对路径（统一用 /），跨盘或算不出来时退化为文件名。"""
    base = base if base is not None else os.getcwd()
    try:
        rel = os.path.relpath(path, base)
    except ValueError:
        return os.path.basename(path)
    return rel.replace("\\", "/")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法: python tools/safe_path.py <path> [base]")
        raise SystemExit(2)
    print(safe_relpath(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None))
