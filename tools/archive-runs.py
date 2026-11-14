#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把过了保留期的 run 目录归档到中央产物库（不删任何东西）

规则：目录名以 `YYYY-MM-DD-` 开头的才算一个 run；早于 `--days` 天（按目录名
里的日期算，不是 mtime）就整目录移到 `<dest>/<YYYY-MM>/<原名>`。`_archive`、
`_template` 不动。

目标库必须用 `--dest` 显式给，工具不猜：中央产物库形如
`E:\\data\\openmausbot\\artifacts\\<bot-slug>`，但那是 Windows 本机的约定。
写死成默认值会在 Linux 上变成一条相对路径（`Path(r"E:\\data\\...")` 在 POSIX
上 `is_absolute()` 为假），结果是把 run 挪进仓库里的一个字面量目录
`E:\\data\\...`——不报错、只是找不回来。故不给默认值。

用法：
    python tools/archive-runs.py --dest <目录> [--days 30] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
RUN_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})-")
SKIP = {"_archive", "_template"}


def run_date(name: str):
    m = RUN_RE.match(name)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def archive(root: Path, dest: Path, days: int, dry_run: bool):
    moved, kept, skipped = [], [], []
    if not root.is_dir():
        return {"success": False, "error": f"runs 目录不存在：{root}",
                "moved": [], "kept": [], "skipped": []}

    today = date.today()
    for p in sorted(root.iterdir()):
        if not p.is_dir():
            continue
        if p.name in SKIP:
            skipped.append(p.name)
            continue
        d = run_date(p.name)
        if d is None:
            skipped.append(p.name)
            continue
        age = (today - d).days
        if age <= days:
            kept.append({"name": p.name, "age_days": age})
            continue
        target_dir = dest / f"{d.year:04d}-{d.month:02d}"
        target = target_dir / p.name
        if target.exists():
            skipped.append(f"{p.name}（目标已存在）")
            continue
        if not dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(p), str(target))
        moved.append({"name": p.name, "age_days": age,
                      "to": str(target)})

    return {"success": True, "error": None, "dry_run": dry_run,
            "moved": moved, "kept": kept, "skipped": skipped}


def main():
    ap = argparse.ArgumentParser(description="过期的 run 目录归档到中央产物库")
    ap.add_argument("--root", default=str(ROOT_DIR / "runs"))
    ap.add_argument("--dest", required=True,
                    help="归档目标库，必须显式给（如 E:\\data\\openmausbot\\artifacts\\<bot-slug>）")
    ap.add_argument("--days", type=int, default=30, help="保留天数，默认 30")
    ap.add_argument("--dry-run", action="store_true", help="只报告，不移动")
    args = ap.parse_args()

    out = archive(Path(args.root), Path(args.dest), args.days, args.dry_run)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
