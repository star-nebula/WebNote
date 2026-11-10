#!/usr/bin/env python3
"""外部技能的来源、新鲜度与刷新（browser-skill 等 vendored skill）。

三种模式：

  离线（默认，进 CI）：读 bot.yaml 的 vendored 段，确认副本存在、是真目录不是链接、
                      文件数与记录一致。不联网。
  在线（--online）：  用 bot.yaml 记的 ref 拉上游目录，逐个比 blob sha，报「副本是否被
                      手改」；另报上游 HEAD 是否又前进了。联网，不进 CI。
  刷新（--pull）：    拉上游 HEAD 的目录内容整体覆盖副本、删掉上游已没有的文件，并把
                      ref / snapshot / files 写回 bot.yaml。一条命令完成升版。

真源只有一处：`bot.yaml` 的 `vendored.upstream` + `ref`。上游是 monorepo 时用 `subdir`
指定技能目录。不要再用第二份本地副本（例如技能库里的同名目录）当中转——两份都要维护，
漏一份就会被镜像回旧版。

用法：
    python tools/check_vendor.py              # 离线检查
    python tools/check_vendor.py --online     # 与 bot.yaml 记的代际比对（需要网络 / gh）
    python tools/check_vendor.py --pull       # 升到上游 HEAD 并写回代际
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
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
    """相对路径 -> 字节数。"""
    return {p.relative_to(path).as_posix(): p.stat().st_size for p in sorted(path.rglob("*")) if p.is_file()}


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
        if path.is_symlink() or any(p.is_symlink() for p in path.rglob("*")):
            print("  LINK     副本里有符号链接（必须是真实内容）")
            problems += 1
        files = local_files(path)
        if "SKILL.md" not in files:
            print("  MISSING  缺 SKILL.md")
            problems += 1
        total = sum(files.values())
        print(f"  OK       {len(files)} 个文件 / {total} 字节")
        recorded = v.get("files")
        if recorded is not None and recorded != len(files):
            print(f"  STALE    bot.yaml 记了 {recorded} 个文件，实际 {len(files)}（被手改？跑 --pull 或 --online）")
            problems += 1
        print(f"           上游 {v.get('upstream', '?')} @ {str(v.get('ref', '?'))[:7]}，快照 {v.get('snapshot', '?')}")
    return problems


# --------------------------------------------------------------------------- 网络


def owner_repo(upstream: str) -> str:
    return upstream.rstrip("/").removeprefix("https://github.com/").removesuffix(".git")


def fetch_json(url: str) -> object:
    """优先用已登录的 gh（不受匿名限流），退到 urllib + GITHUB_TOKEN。"""
    api = "https://api.github.com/"
    gh = shutil.which("gh")
    if gh and url.startswith(api):
        proc = subprocess.run(
            [gh, "api", url[len(api) :]],
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


def upstream_tree(upstream: str, subdir: str, ref: str) -> dict[str, str]:
    """上游 subdir 下 相对路径 -> blob sha（git tree API，不逐个下载）。"""
    data = fetch_json(f"https://api.github.com/repos/{owner_repo(upstream)}/git/trees/{ref}?recursive=1")
    prefix = subdir.rstrip("/") + "/"
    return {
        i["path"][len(prefix) :]: i["sha"]
        for i in data.get("tree", [])
        if i["type"] == "blob" and i["path"].startswith(prefix)
    }


def blob_bytes(upstream: str, sha: str) -> bytes:
    """按 blob sha 取原始字节（base64 解出来就是上游文件内容，不经行尾转换）。"""
    data = fetch_json(f"https://api.github.com/repos/{owner_repo(upstream)}/git/blobs/{sha}")
    return base64.b64decode(data["content"])


def local_blob_sha(path: Path) -> str:
    """与 git hash-object 一致：sha1('blob <len>\\0' + content)。"""
    data = path.read_bytes()
    h = hashlib.sha1()
    h.update(b"blob %d\0" % len(data))
    h.update(data)
    return h.hexdigest()


def latest_commit(upstream: str, subdir: str) -> tuple[str, str]:
    data = fetch_json(f"https://api.github.com/repos/{owner_repo(upstream)}/commits?path={subdir}&per_page=1")
    if not data:
        return "", ""
    return data[0]["sha"], data[0]["commit"]["author"]["date"]


# --------------------------------------------------------------------------- 在线比对


def report(rel: str, tree: dict[str, str], path: Path, ref: str) -> int:
    """打印副本与记录代际的差异，返回差异条数。"""
    local = local_files(path)
    changed = [p for p in tree if p in local and tree[p] != local_blob_sha(path / p)]
    added = [p for p in tree if p not in local]
    gone = [p for p in local if p not in tree]
    if not (changed or added or gone):
        print(f"  一致     {len(tree)} 个文件，与记录代际 {ref[:7]} 相符")
        return 0
    print(f"  不一致     上游记录 {len(tree)} / 本地 {len(local)}；改动 {len(changed)}、缺 {len(added)}、多 {len(gone)}")
    for p in changed:
        print(f"    CHANGED  {p}")
    for p in added:
        print(f"    MISSING  {p}")
    for p in gone:
        print(f"    EXTRA    {p}")
    return len(changed) + len(added) + len(gone)


def check_online(entries: list[dict]) -> int:
    bad = 0
    for v in entries:
        rel, upstream, subdir = v["path"], v["upstream"], v["subdir"]
        ref = str(v.get("ref") or "main")
        print(f"[{rel}] 记录代际 {upstream} {subdir} @ {ref[:7]}")
        try:
            tree = upstream_tree(upstream, subdir, ref)
        except urllib.error.HTTPError as e:
            print(f"  ERROR    GitHub 返回 {e.code}（限流？稍后再试，或用 --pull 走 gh）")
            return 1
        bad += report(rel, tree, ROOT / rel, ref)
        head, when = latest_commit(upstream, subdir)
        if head and head != ref:
            print(f"  上游 HEAD {head[:7]}（{when}）比记录新，可跑 --pull 升版")
    return 1 if bad else 0


# --------------------------------------------------------------------------- 刷新


def record(values: dict[str, dict]) -> None:
    """把 ref / snapshot / files 写回 bot.yaml，保留注释与顺序。"""
    lines = BOT_YAML.read_text(encoding="utf-8").splitlines()
    current: dict | None = None
    for i, line in enumerate(lines):
        m = re.match(r"\s*-\s*path:\s*(\S+)", line)
        if m:
            current = values.get(m.group(1))
            continue
        if current is None:
            continue
        m = re.match(r"(\s*)(ref|snapshot|files):\s*.*$", line)
        if m:
            lines[i] = f"{m.group(1)}{m.group(2)}: {current[m.group(2)]}"
    BOT_YAML.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def pull(entries: list[dict]) -> int:
    for v in entries:
        rel, upstream, subdir = v["path"], v["upstream"], v["subdir"]
        head, when = latest_commit(upstream, subdir)
        if not head:
            print(f"[{rel}] ERROR 查不到上游提交")
            return 1
        tree = upstream_tree(upstream, subdir, head)
        dest = ROOT / rel
        print(f"[{rel}] 上游 {upstream} {subdir} @ {head[:7]}（{when}），{len(tree)} 个文件")
        written = 0
        for path_in_upstream, sha in sorted(tree.items()):
            target = dest / path_in_upstream
            data = blob_bytes(upstream, sha)
            if target.is_file() and target.read_bytes() == data:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            written += 1
        removed = 0
        for p in sorted(dest.rglob("*"), key=lambda x: len(x.parts), reverse=True):
            if p.is_file() and p.relative_to(dest).as_posix() not in tree:
                p.unlink()
                removed += 1
            elif p.is_dir() and not any(p.iterdir()):
                p.rmdir()
        print(f"  写入 {written} 个、删除 {removed} 个")
        record({rel: {"ref": head, "snapshot": date.today().isoformat(), "files": len(tree)}})
        print(f"  已回写 bot.yaml：ref {head[:7]} / snapshot {date.today().isoformat()} / files {len(tree)}")
    return 0


# --------------------------------------------------------------------------- 入口


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="外部技能来源、新鲜度与刷新")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--online", action="store_true", help="与 bot.yaml 记的代际比对（需联网）")
    group.add_argument("--pull", action="store_true", help="升到上游 HEAD 并写回代际（需联网）")
    args = ap.parse_args(argv)

    import yaml

    bot = yaml.safe_load(BOT_YAML.read_text(encoding="utf-8")) or {}
    entries = bot.get("vendored") or []
    if not entries:
        print("bot.yaml 没有 vendored 段，跳过")
        return 0

    if args.pull:
        return pull(entries)
    if args.online:
        return check_online(entries)

    problems = check_offline(entries)
    if problems:
        print(f"\n{problems} 个问题")
        return 1
    print("\n离线检查通过（比对代际：--online；升版：--pull）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
