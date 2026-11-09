#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 agents/ 与 steps/ 从 skill 目录移到项目根，并同步全项目引用。

背景：角色定义与操作卡是**流程资产**，不属于某个 skill 的内部实现。
放在 skills/webnote-workflow/ 下语义上是"这个 skill 的私有物"，且无法与
各 AI 工具的注册位（.workbuddy/agents/、.claude/agents/）对齐。
移到项目根后，路径与各注册位语义一致。

用法：
    python _agent_scripts/move-definitions-to-root.py --dry-run
    python _agent_scripts/move-definitions-to-root.py
"""

import argparse
import shutil
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent.parent
SKILL_DIR = ROOT / "skills" / "webnote-workflow"

MOVES = ["agents", "steps"]

# 全局替换：去掉 skill 目录前缀，改为项目根相对路径
REPLACEMENTS = [
    ("skills/webnote-workflow/agents/", "agents/"),
    ("skills/webnote-workflow/steps/", "steps/"),
]

SKIP_DIRS = {".git", "runs", "__pycache__", "node_modules"}


def iter_markdown():
    for p in ROOT.rglob("*.md"):
        if SKIP_DIRS & set(p.parts):
            continue
        yield p


def main():
    parser = argparse.ArgumentParser(description="定义文件移到项目根并同步引用")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    dry = args.dry_run

    print(f"{'[DRY-RUN] ' if dry else ''}项目根：{ROOT}\n")

    print("— 移动目录 —")
    for name in MOVES:
        src, dst = SKILL_DIR / name, ROOT / name
        if src.exists() and not dst.exists():
            print(f"  skills/webnote-workflow/{name}/ → {name}/")
            if not dry:
                shutil.move(str(src), str(dst))
        elif dst.exists():
            print(f"  已在根目录，跳过：{name}/")
        else:
            print(f"  跳过（不存在）：{name}/")

    print("\n— 更新引用 —")
    touched = []
    for md in iter_markdown():
        original = md.read_text(encoding="utf-8")
        text = original
        for old, new in REPLACEMENTS:
            text = text.replace(old, new)
        if text != original:
            touched.append(md.relative_to(ROOT))
            print(f"  {md.relative_to(ROOT)}")
            if not dry:
                md.write_text(text, encoding="utf-8")
    print(f"\n共更新 {len(touched)} 个文件。")

    print("\n— 残留检查 —")
    leftovers = []
    for md in iter_markdown():
        for i, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
            if "skills/webnote-workflow/agents" in line or "skills/webnote-workflow/steps" in line:
                leftovers.append((md.relative_to(ROOT), i, line.strip()[:90]))
    if leftovers:
        print(f"发现 {len(leftovers)} 处残留：")
        for src, lineno, line in leftovers:
            print(f"  {src}:{lineno}\n      {line}")
    else:
        print("无残留。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
