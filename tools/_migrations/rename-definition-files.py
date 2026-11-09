#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 agents/ 与 steps/ 下的定义文件改名为英文名（去掉序号），并同步更新全项目引用。

背景：agent 定义文件原用「序号 + 中文角色名」（如 01-归类师.md），
英文读者不易理解，故改为纯英文语义名（classifier / distiller / verifier）。

用法（先 dry-run 再实跑）：
    python _agent_scripts/rename-definition-files.py --dry-run
    python _agent_scripts/rename-definition-files.py

只处理 .md，跳过 .git/ 与 runs/（runs/ 是历史档案且被 .gitignore 忽略，保持原貌）。
"""

import argparse
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent.parent
SKILL_DIR = ROOT / "skills" / "webnote-workflow"

# 文件名重命名：(所在目录, 旧名, 新名)
RENAMES = [
    (SKILL_DIR / "agents", "01-归类师.md", "classifier.md"),
    (SKILL_DIR / "agents", "02-笔记匠.md", "distiller.md"),
    (SKILL_DIR / "agents", "03-核查官.md", "verifier.md"),
    (SKILL_DIR / "steps", "00-采编.md", "collect.md"),
    (SKILL_DIR / "steps", "00-采编-图片.md", "collect-image.md"),
    (SKILL_DIR / "steps", "00-采编-视频音频.md", "collect-video-audio.md"),
    (SKILL_DIR / "steps", "04-确认.md", "confirm.md"),
]

# 正文替换（按长度降序，避免子串误伤）
REPLACEMENTS = [
    ("agents/03-核查官.md", "agents/verifier.md"),
    ("agents/02-笔记匠.md", "agents/distiller.md"),
    ("agents/01-归类师.md", "agents/classifier.md"),
    ("steps/00-采编-视频音频.md", "steps/collect-video-audio.md"),
    ("steps/00-采编-图片.md", "steps/collect-image.md"),
    ("steps/00-采编.md", "steps/collect.md"),
    ("steps/04-确认.md", "steps/confirm.md"),
    # steps 内部的交叉引用不带目录前缀
    ("00-采编-视频音频.md", "collect-video-audio.md"),
    ("00-采编-图片.md", "collect-image.md"),
    # frontmatter 内的角色标识
    ("name: 03-核查官", "name: verifier"),
    ("name: 02-笔记匠", "name: distiller"),
    ("name: 01-归类师", "name: classifier"),
    ("- 02-笔记匠", "- distiller"),
]

SKIP_DIRS = {".git", "runs", "__pycache__", "node_modules"}


def iter_markdown():
    for p in ROOT.rglob("*.md"):
        if SKIP_DIRS & set(p.parts):
            continue
        yield p


def main():
    parser = argparse.ArgumentParser(description="定义文件改英文名并同步引用")
    parser.add_argument("--dry-run", action="store_true", help="只报告将做什么，不实际改动")
    args = parser.parse_args()

    dry = args.dry_run
    print(f"{'[DRY-RUN] ' if dry else ''}项目根：{ROOT}\n")

    # 1. 重命名文件
    print("— 重命名文件 —")
    for directory, old, new in RENAMES:
        src, dst = directory / old, directory / new
        if not src.exists():
            print(f"  跳过（不存在）：{src.relative_to(ROOT)}")
            continue
        print(f"  {old} → {new}")
        if not dry:
            src.rename(dst)

    # 2. 同步引用
    print("\n— 更新引用 —")
    touched = 0
    for md in iter_markdown():
        text = original = md.read_text(encoding="utf-8")
        for old, new in REPLACEMENTS:
            text = text.replace(old, new)
        if text != original:
            touched += 1
            print(f"  {md.relative_to(ROOT)}")
            if not dry:
                md.write_text(text, encoding="utf-8")

    print(f"\n共更新 {touched} 个文件。")

    # 3. 残留检查
    print("\n— 残留检查 —")
    leftovers = []
    for md in iter_markdown():
        for i, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
            for old, _ in REPLACEMENTS:
                if old.startswith(("agents/", "steps/")) and old in line:
                    leftovers.append((md.relative_to(ROOT), i, line.strip()[:90]))
                    break
    if leftovers:
        print(f"发现 {len(leftovers)} 处残留（需人工确认）：")
        for src, lineno, line in leftovers:
            print(f"  {src}:{lineno}")
            print(f"      {line}")
    else:
        print("无残留。")

    return 0


if __name__ == "__main__":
    sys.exit(main())
