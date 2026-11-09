"""仓库不变量：CI 与本地跑同一套。

跑法：python -m pytest tests -q

只断言「改了会静默变坏」的东西：
  - 生成物与真源一致（AGENTS.public.md）
  - 私有路径不泄漏
  - 产出表头 ↔ 步骤卡一致（六处手抄同一份契约，靠它兜住）
  - 外部技能副本真实、来源可查、主体指向的 references 都在
不测「文件在不在」——git 已经是那个断言的来源。
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
STEPS_DIR = "skills/webnote-workflow/references/steps"

# 契约文件：路径 → frontmatter 里必须有的字段（空列表 = 只要求存在）
CONTRACT = {
    "skills/webnote-workflow/SKILL.md": ["name:", "description:"],
    "skills/web-archive/SKILL.md": ["name:", "description:"],
    "skills/image-extract/SKILL.md": ["name:", "description:"],
    "skills/video-extract/SKILL.md": ["name:", "description:"],
    f"{STEPS_DIR}/collect.md": [],
    f"{STEPS_DIR}/collect-image.md": [],
    f"{STEPS_DIR}/collect-video-audio.md": [],
    f"{STEPS_DIR}/collect-web-archive.md": [],
    f"{STEPS_DIR}/confirm.md": [],
    "agents/classifier.md": ["description:", "context:"],
    "agents/distiller.md": ["description:", "context:"],
    "agents/verifier.md": ["description:", "context:"],
}

LEAK_PATTERNS = [
    r"[A-Za-z]:\\knowledge",
    r"[A-Za-z]:\\Projects\\Github",
    r"[A-Za-z]:\\Users\\[A-Za-z0-9_.-]+",
    r"\bHermes\b",
]
# 历史快照与测试自身可以出现旧路径
LEAK_EXEMPT_PREFIX = ("tests/", "docs/versions/")
BINARY_SUFFIX = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".wav", ".pdf", ".ico"}


def tracked_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    return [ROOT / p.decode("utf-8") for p in out.split(b"\0") if p]


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="ignore")


def test_contract_files_present():
    missing, bad = [], []
    for rel, fields in CONTRACT.items():
        p = ROOT / rel
        if not p.is_file():
            missing.append(rel)
            continue
        head = read(p)[:1200]
        for field in fields:
            if field not in head:
                bad.append(f"{rel} 缺 {field}")
    assert not missing, "契约文件缺失：\n" + "\n".join(missing)
    assert not bad, "frontmatter 不完整：\n" + "\n".join(bad)


def test_public_agents_in_sync():
    if not (ROOT / "AGENTS.md").is_file():
        pytest.skip("本地没有私有 AGENTS.md（公开克隆），跳过")
    r = subprocess.run(
        [sys.executable, "tools/sync-agents-public.py", "--check"], cwd=ROOT, capture_output=True, text=True
    )
    assert r.returncode == 0, (r.stdout + r.stderr).strip()


def test_no_private_path_leak():
    hits = []
    for p in tracked_files():
        rel = p.relative_to(ROOT).as_posix()
        if rel.startswith(LEAK_EXEMPT_PREFIX) or rel == "tools/sync-agents-public.py":
            continue
        if not p.is_file() or p.suffix in BINARY_SUFFIX:
            continue
        for i, line in enumerate(read(p).splitlines(), 1):
            for pat in LEAK_PATTERNS:
                if re.search(pat, line):
                    hits.append(f"{rel}:{i}: {line.strip()[:90]}")
    assert not hits, "私有路径 / 身份泄漏：\n" + "\n".join(hits)


def test_no_legacy_paths():
    legacy = ["_agent_scripts", "Webpage note workflow.md"]
    ext = {".md", ".py", ".ps1", ".yml", ".yaml", ".json", ".toml", ".cfg"}
    hits = []
    for p in tracked_files():
        rel = p.relative_to(ROOT).as_posix()
        if rel.startswith(LEAK_EXEMPT_PREFIX) or rel.startswith("tools/_migrations/"):
            continue
        if not p.is_file() or p.suffix not in ext:
            continue
        text = read(p)
        for pat in legacy:
            if pat in text:
                hits.append(f"{rel} 仍引用旧路径 {pat}")
    assert not hits, "旧路径残留：\n" + "\n".join(hits)


# runs/_template/ 的空骨架 ↔ 它的规范出处。表头改了任何一边都必须同步另一边。
RUN_TEMPLATE = {
    "00-采编清单.md": (
        f"{STEPS_DIR}/collect.md",
        ["| ID | 标题 | 域名 | 媒体格式 | 正文字符数 | 有正文 | 提取方式 | 提取结果 | 原文来源 |"],
    ),
    "01-整理清单.md": (
        "agents/classifier.md",
        ["| ID | 标题 | 域名 | 媒体格式 | 正文字符数 | 有正文 | 分类 | 原文来源 |"],
    ),
    "02-笔记.md": (
        "agents/distiller.md",
        ["**为什么值得保留**：", "**修订建议**：", "（出处：第 3 段 · 原文）"],
    ),
    "03-核查表.md": (
        "agents/verifier.md",
        ["| 条目 | 状态 | 来源类型 | 正文依据 |", "## 需用户回看的条目", "| 条目 | 状态 | 为什么需要回看 |"],
    ),
    "04-待确认提案.md": (
        f"{STEPS_DIR}/confirm.md",
        ["| 条目 | 建议动作 | 依据 |", "| 条目 | 问题 | 建议动作 |", "## 待你确认的落地动作"],
    ),
}


@pytest.mark.parametrize("name", sorted(RUN_TEMPLATE))
def test_run_template_matches_step_cards(name):
    """新 run 的空骨架必须与步骤卡定义一致，防止每份产出的表头自己漂移。"""
    source, needles = RUN_TEMPLATE[name]
    src = read(ROOT / source)
    tpl_path = ROOT / "runs/_template" / name
    assert tpl_path.is_file(), f"runs/_template/{name} 缺失"
    tpl = read(tpl_path)
    for needle in needles:
        assert needle in src, f"{source} 里找不到 {needle!r}（规范改了，模板与测试要一起改）"
        assert needle in tpl, f"runs/_template/{name} 里找不到 {needle!r}"


def test_run_template_is_tracked_not_ignored():
    """骨架必须进 git：runs/* 的忽略规则不得把它吞掉。"""
    target = "runs/_template/00-采编清单.md"
    res = subprocess.run(["git", "check-ignore", target], cwd=ROOT, capture_output=True, text=True)
    assert res.returncode == 1, f"{target} 被 .gitignore 忽略了，需要 !runs/_template/** 例外"


def test_vendored_skill_is_a_real_copy():
    """外部技能必须是真副本：不是链接，且来源声明是 copy 模式、只同步它一个。"""
    vendored = ROOT / "skills/browser-skill"
    assert vendored.is_dir() and not vendored.is_symlink(), "skills/browser-skill 必须是真实目录"
    assert "name: browser-skill" in read(vendored / "SKILL.md")[:400], "副本缺 frontmatter 或名字不对"

    cfg = yaml.safe_load((ROOT / ".skillshare/config.yaml").read_text(encoding="utf-8")) or {}
    targets = cfg.get("targets") or []
    assert len(targets) == 1, "只允许一个 vendored target"
    skills = targets[0].get("skills") or {}
    assert skills.get("mode") == "copy", "必须 copy 模式，symlink 会让仓库依赖外部路径"
    assert skills.get("include") == ["browser-skill"], "只同步 browser-skill，别把整个技能库拖进来"


def test_vendored_manifest_records_upstream():
    """外部技能的真源必须记在 bot.yaml：上游仓库 + 具体 commit + 快照日期。

    .skillshare/config.yaml 只说明「从哪里 copy」，说不清「上游是哪一代」；
    exe 版本号也不行（别人不一定有那个 exe）。
    """
    bot = yaml.safe_load((ROOT / "bot.yaml").read_text(encoding="utf-8")) or {}
    entries = bot.get("vendored") or []
    assert entries, "bot.yaml 缺 vendored 段（外部技能的来源声明）"

    cfg = yaml.safe_load((ROOT / ".skillshare/config.yaml").read_text(encoding="utf-8")) or {}
    included = (cfg["targets"][0]["skills"] or {}).get("include") or []

    for v in entries:
        where = f"vendored: {v.get('path')}"
        assert v["upstream"].startswith("https://github.com/"), f"{where} 的 upstream 必须是仓库地址"
        assert re.fullmatch(r"[0-9a-f]{40}", str(v["ref"])), f"{where} 的 ref 必须是完整 commit sha"
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(v["snapshot"])), f"{where} 的 snapshot 必须是日期"
        assert Path(v["path"]).name in included, f"{where} 没在 .skillshare 的 include 里（两边对不上）"

        path = ROOT / v["path"]
        assert path.is_dir(), f"{where} 副本目录不存在"
        assert not any(p.is_symlink() for p in path.rglob("*")), f"{where} 里不该有符号链接"


@pytest.mark.parametrize("name", ["browser-skill"])
def test_vendored_references_all_reachable(name):
    """上游 2026-11 起是「主体 + references」，主体必须把每个 references 文件都指到。

    只同步一半（比如只覆盖 SKILL.md）会让 agent 读到指向不存在文件的引用。
    """
    skill = ROOT / "skills" / name
    refs = {p.name for p in (skill / "references").glob("*.md")}
    assert refs, f"skills/{name}/references 为空（上游布局是 SKILL.md + references/）"
    linked = set(re.findall(r"references/([\w-]+\.md)", read(skill / "SKILL.md")))
    assert refs <= linked, f"SKILL.md 没有引用到：{sorted(refs - linked)}"

def test_memory_stays_private():
    """长期记忆只在本机：/memory/ 必须被 gitignore，且不得有任何文件被跟踪。"""
    probe = ROOT / "memory" / "MEMORY.md"
    if probe.exists():
        r = subprocess.run(["git", "check-ignore", "-q", str(probe)], cwd=ROOT)
        assert r.returncode == 0, "memory/ 必须被 .gitignore 忽略（仓库是公开的）"
    tracked = subprocess.run(
        ["git", "ls-files", "memory"], cwd=ROOT, capture_output=True, text=True
    ).stdout.strip()
    assert not tracked, f"memory/ 下不应有被跟踪文件：{tracked}"
