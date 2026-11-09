#!/usr/bin/env python3
"""WebNote 自检与接线。

    python tools/doctor.py           # 报告：本工具能用什么、缺什么
    python tools/doctor.py --wire     # 为当前工具生成/刷新注册面（幂等）
    python tools/doctor.py --check    # 只校验：生成物是否与真源一致（CI 用，不一致 exit 1）

真源只有两处：
    bot.yaml      —— 角色注册信息（工具白名单、写入边界、是否要独立上下文）
    agents/*.md   —— 角色定义正文与 description
生成物（.claude/agents/*.md）一律由本脚本产出，禁止手改。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("需要 PyYAML：python -m pip install pyyaml")

ROOT = Path(__file__).resolve().parent.parent
BOT = ROOT / "bot.yaml"
GUARD = Path("tools/hooks/guard_write.py")

GENERATED_NOTE = "本文件由 `python tools/doctor.py --wire` 生成，勿手改。"

SETTINGS = ROOT / ".claude" / "settings.json"
HOOK_MATCHER = "Write|Edit|MultiEdit|NotebookEdit"
HOOK_CMD = 'python "$CLAUDE_PROJECT_DIR/tools/hooks/guard_write.py"'

BLOCK_START = "<!-- bot:start"
BLOCK_END = "<!-- bot:end -->"


# ---------- 真源读取 ----------

def load_bot() -> dict:
    with BOT.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def frontmatter(path: Path) -> dict:
    """取 markdown 文件的 YAML frontmatter（没有则空 dict）。"""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    try:
        return yaml.safe_load(text[3:end]) or {}
    except yaml.YAMLError:
        return {}


# ---------- 生成 ----------

def render_claude_agents(bot: dict) -> dict[str, str]:
    """按 bot.yaml + agents/*.md 生成 .claude/agents/<name>.md 的内容。"""
    out: dict[str, str] = {}
    for role in bot.get("roles", []):
        name = role["name"]
        src = ROOT / role["path"]
        if not src.exists():
            raise SystemExit(f"角色定义缺失：{role['path']}")
        desc = (frontmatter(src).get("description") or "").strip().splitlines()
        desc = desc[0].strip() if desc else role.get("title", name)
        desc = f"{desc}（执行前必读 {role['path']}）"

        tools = ", ".join(role.get("tools", []))
        denied = ", ".join(role.get("disallowed_tools", []))
        scope = role.get("write_scope", "")

        block = [
            "---",
            f"name: {name}",
            f"description: {desc}",
        ]
        if tools:
            block.append(f"tools: {tools}")
        if denied:
            block.append(f"disallowedTools: {denied}")
        block += [
            "---",
            "",
            GENERATED_NOTE,
            "",
            f"角色定义、契约字段（reads / writes / forbidden）与铁律见 `{role['path']}`，执行前必读。",
        ]
        if role.get("fresh_context"):
            block.append("**必须在全新上下文中运行**，不得携带撰写者的结论。")
        if scope:
            block.append(f"写入边界由项目级 hook 强制（`.claude/settings.json` → `tools/hooks/guard_write.py`）：只允许写 `{scope}`。")
        out[f"{name}.md"] = "\n".join(block) + "\n"
    return out


def render_machine_block(bot: dict) -> str:
    """AGENTS.md 里那段机器块（由 bot.yaml 生成）。"""
    lines = [
        f"{BLOCK_START} 由 bot.yaml 生成，勿手改；改完跑 python tools/doctor.py --wire -->",
        "",
        "角色（需要时读定义文件，按其 reads / writes / forbidden 执行）：",
        "",
        "| 角色 | 定义 | 可写 | 独立上下文 |",
        "|---|---|---|---|",
    ]
    for r in bot.get("roles", []):
        fresh = "必须" if r.get("fresh_context") else "否"
        lines.append(f"| `{r['name']}` | `{r['path']}` | `{r.get('write_scope', '-')}` | {fresh} |")

    lines += ["", "技能（开工先读对应 SKILL.md，只做路由）：", ""]
    for s in bot.get("skills", []):
        lines.append(f"- `{s['name']}` → `{s['path']}/SKILL.md`")

    vendored = bot.get("vendored") or []
    if vendored:
        lines += ["", "外部技能（真源不在本仓，别改内容，按需读）：", ""]
        for v in vendored:
            lines.append(
                f"- `{v['path']}` ← {v.get('upstream', '')}"
                f" @ {str(v.get('ref', ''))[:7]}（快照 {v.get('snapshot', '?')}，{v.get('layout', '')}）"
            )

    lines += ["", "流程："]
    for f in bot.get("flows", []):
        lines.append(f"- `{f['id']}`（{f.get('title', '')}）：{' → '.join(f.get('steps', []))}")

    lines += ["", "命令："]
    for k, v in (bot.get("commands") or {}).items():
        lines.append(f"- `{v}`  — {k}")

    lines += [BLOCK_END]
    return "\n".join(lines)


def sync_machine_block(bot: dict, write: bool) -> tuple[bool, str]:
    """把机器块写进 AGENTS.md（write=False 时只比对）。返回 (是否最新, 说明)。"""
    entry = ROOT / (bot.get("entry") or "AGENTS.md")
    if not entry.exists():
        return True, "无入口文件，跳过"
    text = entry.read_text(encoding="utf-8")
    start = text.find(BLOCK_START)
    end = text.find(BLOCK_END)
    if start == -1 or end == -1:
        return True, f"{entry.name} 无机器块标记，跳过"
    end += len(BLOCK_END)
    new = text[:start] + render_machine_block(bot) + text[end:]
    if new == text:
        return True, "机器块一致"
    if write:
        entry.write_text(new, encoding="utf-8", newline="\n")
        return False, f"已更新 {entry.name} 机器块"
    return False, f"{entry.name} 机器块与本文件不一致"


def agent_dir(bot: dict, surface: str = "claude") -> Path:
    spec = (bot.get("surfaces") or {}).get(surface) or {}
    return ROOT / spec.get("dir", f".{surface}/agents")


def ensure_settings(write: bool) -> tuple[bool, str]:
    """把写入守卫挂到 .claude/settings.json 的 PreToolUse（幂等合并，不动其他配置）。"""
    data: dict = {}
    if SETTINGS.exists():
        try:
            data = json.loads(SETTINGS.read_text(encoding="utf-8") or "{}")
        except json.JSONDecodeError:
            return False, f"{SETTINGS.name} 不是合法 JSON，未改动"

    pre = data.setdefault("hooks", {}).setdefault("PreToolUse", [])
    found = None
    for entry in pre:
        for hook in entry.get("hooks", []):
            if "guard_write.py" in str(hook.get("command", "")):
                found = entry
                break
        if found:
            break

    want = {"matcher": HOOK_MATCHER, "hooks": [{"type": "command", "command": HOOK_CMD}]}
    if found == want:
        return True, "settings.json 守卫已就位"

    if found is None:
        pre.append(want)
    else:
        found.clear()
        found.update(want)

    if not write:
        return False, "settings.json 守卫缺失或与模板不一致"

    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return False, "已更新 settings.json 守卫"


# ---------- 工具检测 ----------

def detect_tool() -> tuple[str, str]:
    env = os.environ
    if env.get("CLAUDECODE") or env.get("CLAUDE_CODE_ENTRYPOINT") or env.get("CLAUDE_PROJECT_DIR"):
        return "Claude Code", "agent-files"
    if any(k.startswith("PI_") for k in env):
        return "pi", "read-only"
    if env.get("CODEX_SANDBOX") or env.get("CODEX_HOME") or env.get("CODEX_MANAGED_BY_NPM"):
        return "Codex", "read-only"
    if env.get("WORKBUDDY") or env.get("WB_SESSION"):
        return "WorkBuddy", "read-only"
    return "未知工具", "read-only"


# ---------- 命令 ----------

def cmd_report(bot: dict) -> int:
    tool, mode = detect_tool()
    problems: list[str] = []

    print(f"仓库：{ROOT}")
    print(f"工具：{tool}（注册方式：{mode}）")
    if mode == "read-only":
        print("  → 走零注册基线：按 AGENTS.md 的派发表读 agents/<name>.md 自行执行，无需任何安装。")

    print("\n角色：")
    for role in bot.get("roles", []):
        ok = (ROOT / role["path"]).exists()
        mark = "✔" if ok else "✘"
        fresh = " · 需独立上下文" if role.get("fresh_context") else ""
        print(f"  {mark} {role['name']:<12} {role['path']}  写入 {role.get('write_scope','-')}{fresh}")
        if not ok:
            problems.append(f"角色文件缺失：{role['path']}")

    print("\n技能：")
    for skill in bot.get("skills", []):
        p = ROOT / skill["path"] / "SKILL.md"
        ok = p.exists()
        print(f"  {'✔' if ok else '✘'} {skill['name']:<20} {skill['path']}/SKILL.md")
        if not ok:
            problems.append(f"技能缺失：{skill['path']}/SKILL.md")

    print("\n生成物：")
    block_ok, block_msg = sync_machine_block(bot, write=False)
    print(f"  {'✔' if block_ok else '✘'} AGENTS.md 机器块：{block_msg}")
    if not block_ok:
        problems.append(block_msg)

    drift = check_generated(bot, quiet=True)
    if drift:
        print(f"  ✘ .claude/agents 有 {len(drift)} 处与真源不一致：{', '.join(drift)}")
        print("    → 运行 python tools/doctor.py --wire")
        problems += [f"生成物过期：{n}" for n in drift]
    else:
        print("  ✔ .claude/agents 与 bot.yaml + agents/*.md 一致")

    guard_ok = (ROOT / GUARD).exists()
    print(f"\n写入守卫：{'✔' if guard_ok else '✘'} {GUARD}")
    hook_ok, hook_msg = ensure_settings(write=False)
    print(f"  {'✔' if hook_ok else '✘'} 挂载：{hook_msg}")
    if not hook_ok:
        problems.append(hook_msg)

    if problems:
        print("\n需要处理：")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("\n一切就绪。")
    return 0


def check_generated(bot: dict, quiet: bool = False) -> list[str]:
    """返回与真源不一致的文件名列表（含已多余、已缺失、内容不同）。"""
    want = render_claude_agents(bot)
    d = agent_dir(bot)
    have = {p.name for p in d.glob("*.md")} if d.exists() else set()
    drift = sorted(name for name in want if not (d / name).exists()
                   or (d / name).read_text(encoding="utf-8") != want[name])
    drift += sorted(have - set(want))
    return drift


def cmd_wire(bot: dict) -> int:
    want = render_claude_agents(bot)
    d = agent_dir(bot)
    d.mkdir(parents=True, exist_ok=True)

    changed = []
    for name, content in want.items():
        p = d / name
        if p.exists() and p.read_text(encoding="utf-8") == content:
            continue
        p.write_text(content, encoding="utf-8", newline="\n")
        changed.append(name)

    for p in d.glob("*.md"):
        if p.name not in want:
            p.unlink()
            changed.append(f"-{p.name}")

    if changed:
        print(f"已更新 .claude/agents：{', '.join(changed)}")
    else:
        print("已是最新，无需改动。")

    _, msg = sync_machine_block(bot, write=True)
    print(msg)
    _, msg = ensure_settings(write=True)
    print(msg)
    return 0


def cmd_check(bot: dict) -> int:
    bad = False
    drift = check_generated(bot)
    if drift:
        bad = True
        print("生成物与真源不一致：" + ", ".join(drift))
    block_ok, block_msg = sync_machine_block(bot, write=False)
    if not block_ok:
        bad = True
        print(block_msg)
    hook_ok, hook_msg = ensure_settings(write=False)
    if not hook_ok:
        bad = True
        print(hook_msg)
    if bad:
        print("运行 python tools/doctor.py --wire 后提交。")
        return 1
    print("生成物与机器块一致。")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--wire", action="store_true", help="为当前工具生成/刷新注册面")
    g.add_argument("--check", action="store_true", help="校验生成物是否与真源一致")
    args = ap.parse_args(argv)

    bot = load_bot()
    if args.wire:
        return cmd_wire(bot)
    if args.check:
        return cmd_check(bot)
    return cmd_report(bot)


if __name__ == "__main__":
    sys.exit(main())
