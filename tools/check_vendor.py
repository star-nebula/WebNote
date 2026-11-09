#!/usr/bin/env python3
"""外部技能的来源与新鲜度检查（browser-skill 等 vendored skill）。

两种模式：

  离线（默认，进 CI）：读 bot.yaml 的 vendored 段，确认副本存在、是真目录不是链接、
                      文件数/字节数与上次记录一致。不联网。
  在线（--online）：  拉上游仓库对应目录的文件清单与内容，逐个比 sha256，报
                      落后/新增/删除。会联网，可能被限流，所以不进 CI。

用法：
    python tools/check_vendor.py              # 离线检查
    python tools/check_vendor.py --online     # 与上游比对（需要网络）
    python tools/check_vendor.py --online --update   # 比对通过后把 ref/snapshot 写回 bot.yaml
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOT_YAML = ROOT / "bot.yaml"
UA = {"User-Agent": "webnote-vendor-check"}


# --------------------------------------------------------------------------- 离线


def local_files(path: Path) -> dict[str, int]:
    """相对路径 -> 字节数。跳过 .git 之类。"""
    out: dict[str, int] = {}
    for p in sorted(path.rglob("*")):
        if p.is_file():
            out[p.relative_to(path).as_posix()] = p.stat().st_size
    return out


def check_offline(entries: list[dict]) -> int:
    problems = 0
    for v in entries:
        rel = v["path"]
        path = ROOT / rel
        print(f"[{rel}]")
        if not path.is_dir():
            print("  MISSING  副本目录不存在")
            problems += 1
            continue
        links = [p for p in path.rglob("*") if p.is_symlink()]
        if links or path.is_symlink():
            print(f"  LINK     副本里有 {len(links)} 条符号链接（必须是真实内容）")
            problems += 1
        files = local_files(path)
        if "SKILL.md" not in files:
            print("  MISSING  缺 SKILL.md")
            problems += 1
        total = sum(files.values())
        print(f"  OK       {len(files)} 个文件 / {total} 字节")
        recorded = v.get("files")
        if recorded is not None and recorded != len(files):
            print(f"  STALE    bot.yaml 记了 {recorded} 个文件，实际 {len(files)}")
            problems += 1
        print(f"           上游 {v.get('upstream', '?')} @ {str(v.get('ref', '?'))[:7]}，快照 {v.get('snapshot', '?')}")
    return problems


# --------------------------------------------------------------------------- 在线


def fetch_json(url: str) -> object:
    """优先用已登录的 gh（不受匿名限流），退到 urllib + GITHUB_TOKEN。"""
    gh = shutil.which("gh")
    if gh and url.startswith("https://api.github.com/"):
        proc = subprocess.run(
            [gh, "api", url[len("https://api.github.com/"):]],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if proc.returncode == 0:
            return json.loads(proc.stdout)
        if "auth" not in proc.stderr.lower():
            raise urllib.error.HTTPError(url, 403, proc.stderr.strip()[:120], None, None)
    headers = dict(UA)
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def fetch_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def upstream_tree(upstream: str, subdir: str, ref: str) -> dict[str, str]:
    """上游目录下 相对路径 -> blob sha（用 git tree API，避免逐个下载）。"""
    owner_repo = upstream.rstrip("/").removeprefix("https://github.com/")
    for base in (f"https://api.github.com/repos/{owner_repo}/git/trees/{ref}?recursive=1",):
        data = fetch_json(base)
        tree = {i["path"]: i["sha"] for i in data.get("tree", []) if i["type"] == "blob"}
    prefix = subdir.rstrip("/") + "/"
    return {p[len(prefix):]: sha for p, sha in tree.items() if p.startswith(prefix)}


def local_blob_sha(path: Path) -> str:
    """与 git hash-object 一致：sha1('blob <len>\\0' + content)。"""
    data = path.read_bytes()
    h = hashlib.sha1()
    h.update(b"blob %d\0" % len(data))
    h.update(data)
    return h.hexdigest()


def latest_commit(upstream: str, subdir: str) -> tuple[str, str]:
    owner_repo = upstream.rstrip("/").removeprefix("https://github.com/")
    url = f"https://api.github.com/repos/{owner_repo}/commits?path={subdir}&per_page=1"
    data = fetch_json(url)
    if not data:
        return "", ""
    return data[0]["sha"], data[0]["commit"]["author"]["date"]


def check_online(entries: list[dict]) -> int:
    for v in entries:
        rel, upstream, subdir, ref = v["path"], v["upstream"], v["subdir"], str(v.get("ref", "main"))
        path = ROOT / rel
        print(f"[{rel}] 上游 {upstream} {subdir} @ {ref[:7]}")
        try:
            tree = upstream_tree(upstream, subdir, ref)
        except urllib.error.HTTPError as e:
            print(f"  ERROR    GitHub 返回 {e.code}（限流？稍后再试或换 --ref）")
            return 1
        local = local_files(path)
        changed = [p for p in tree if p in local and tree[p] != local_blob_sha(path / p)]
        added = [p for p in tree if p not in local]
        gone = [p for p in local if p not in tree]
        head, when = latest_commit(upstream, subdir)
        if not (changed or added or gone):
            print(f"  最新     与上游一致（{len(tree)} 个文件）")
        else:
            print(f"  落后     上游 {len(tree)} / 本地 {len(local)}；改动 {len(changed)}、新增 {len(added)}、上游已删 {len(gone)}")
            for p in changed:
                print(f"    CHANGED  {p}")
            for p in added:
                print(f"    ADDED    {p}")
            for p in gone:
                print(f"    REMOVED  {p}")
        if head and head != ref:
            print(f"  上游 HEAD {head[:7]} ({when})，本仓记的是 {ref[:7]}")
    return 0


def update_records(entries: list[dict]) -> None:
    """把上游 HEAD 与今天写回 bot.yaml（仅在 --online 比对后手动使用）。"""
    text = BOT_YAML.read_text(encoding="utf-8")
    for v in entries:
        head, _ = latest_commit(v["upstream"], v["subdir"])
        if not head:
            continue
        text = text.replace(str(v.get("ref", "")), head)
        old_snap = str(v.get("snapshot", ""))
        text = text.replace(f"snapshot: {old_snap}", f"snapshot: {date.today().isoformat()}")
        print(f"  已更新 {v['path']} -> {head[:7]} / {date.today().isoformat()}")
    BOT_YAML.write_text(text, encoding="utf-8", newline="\n")


# --------------------------------------------------------------------------- 入口


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="外部技能来源与新鲜度检查")
    ap.add_argument("--online", action="store_true", help="与上游仓库比对（需联网）")
    ap.add_argument("--update", action="store_true", help="比对后把上游 HEAD 写回 bot.yaml")
    args = ap.parse_args(argv)

    import yaml

    bot = yaml.safe_load(BOT_YAML.read_text(encoding="utf-8")) or {}
    entries = bot.get("vendored") or []
    if not entries:
        print("bot.yaml 没有 vendored 段，跳过")
        return 0

    if not args.online:
        problems = check_offline(entries)
        if problems:
            print(f"\n{problems} 个问题")
            return 1
        print("\n离线检查通过（在线比对：python tools/check_vendor.py --online）")
        return 0

    rc = check_online(entries)
    if args.update and rc == 0:
        update_records(entries)
    return rc


if __name__ == "__main__":
    sys.exit(main())
