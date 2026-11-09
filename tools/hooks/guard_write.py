#!/usr/bin/env python3
"""PreToolUse 写入守卫（Claude Code 项目级 hook）。

由 `.claude/settings.json` 挂到 Write / Edit / MultiEdit 上，从 stdin 读取 Claude Code
传来的 JSON。若本次调用来自某个已知角色（payload 里的 `agent_type`），就按 `bot.yaml`
里该角色的 `write_scope` 校验目标路径；越界 exit 2 —— CC 会中止这次工具调用，并把
stderr 反馈给模型。

为什么挂在 settings.json 而不是 agent frontmatter：实测 CC 2.1.310 不会执行 subagent
frontmatter 里的 `hooks`，但项目级 hook 对 subagent 的写入**会**触发，且 payload 带
`agent_type`，正好够用。

手动测试：
    echo '{"agent_type":"verifier","tool_name":"Write",
           "tool_input":{"file_path":"runs/x/02-笔记.md"}}' | python tools/hooks/guard_write.py
    echo ... | python tools/hooks/guard_write.py --role verifier --scope "runs/*/03-核查表.md"
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import sys
from pathlib import Path

WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
PATH_KEYS = ("file_path", "path", "notebook_path")


def repo_root() -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2]


def load_scopes(root: Path) -> dict[str, list[str]]:
    """从 bot.yaml 读出 {角色名: [可写 glob, ...]}。"""
    try:
        import yaml
    except ImportError:
        return {}
    bot = root / "bot.yaml"
    if not bot.exists():
        return {}
    try:
        data = yaml.safe_load(bot.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    scopes: dict[str, list[str]] = {}
    for role in data.get("roles", []):
        name = role.get("name")
        if not name:
            continue
        raw = role.get("write_scope") or []
        scopes[name] = [raw] if isinstance(raw, str) else list(raw)
    return scopes


def target(raw: str, root: Path) -> str:
    p = Path(raw)
    try:
        return p.resolve().relative_to(root.resolve()).as_posix()
    except (ValueError, OSError):
        return raw.replace("\\", "/")


def matches(rel: str, scope: str) -> bool:
    rel_n, scope_n = rel.replace("\\", "/"), scope.replace("\\", "/")
    return fnmatch.fnmatch(rel_n, scope_n) or fnmatch.fnmatch(rel_n, scope_n.replace("*", "**"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", help="指定角色（默认取 payload 的 agent_type）")
    ap.add_argument("--scope", action="append", default=[], help="可写 glob（默认取 bot.yaml）")
    args = ap.parse_args(argv)

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 0  # 拿不到输入就不拦，避免把自己变成故障点

    tool = payload.get("tool_name") or payload.get("toolName") or ""
    if tool not in WRITE_TOOLS:
        return 0

    role = args.role or payload.get("agent_type") or payload.get("agentType") or ""
    if not role:
        return 0  # 主 agent 不受角色边界约束

    root = repo_root()
    scopes = args.scope or load_scopes(root).get(role) or []
    if not scopes:
        return 0  # 未知角色或该角色没有写入约束

    tinput = payload.get("tool_input") or payload.get("toolInput") or {}
    raw = next((tinput[k] for k in PATH_KEYS if isinstance(tinput.get(k), str) and tinput[k].strip()), "")
    if not raw:
        return 0

    rel = target(raw.strip(), root)

    # runs/_template/ 是进 git 的空骨架：任何角色都不得改写（`runs/*/` 的 glob 会误匹配它）
    if rel.replace("\\", "/").startswith("runs/_template/"):
        print(
            f"[WebNote] 拒绝写入：{rel}\n"
            "`runs/_template/` 是新 run 的空骨架，只读。起新 run 请复制整个目录到 `runs/<日期-主题>/` 再填。",
            file=sys.stderr,
        )
        return 2

    if any(matches(rel, s) for s in scopes):
        return 0

    allowed = "、".join(f"`{s}`" for s in scopes)
    print(
        f"[WebNote] 拒绝写入：{rel}\n"
        f"角色 `{role}` 只能写 {allowed}。\n"
        f"需要改其他文件时，把内容作为回复交回主 agent，不要自己落盘。",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
