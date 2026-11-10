"""仓库不变量：CI 与本地跑同一套。

跑法：python -m pytest tests -q

只断言「改了会静默变坏」的东西：
  - 生成物与真源一致（AGENTS.public.md）
  - 私有路径不泄漏、旧路径不残留
  - 流水线由 `skills/webnote-workflow/steps/` 唯一表达：文件名即顺序，
    每个步骤文件自带格式针（`format_needles`），`runs/_template/` 必须与之一致
  - 三条铁律只在 `docs/architecture.md` 定义，别处只许引用
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
STEPS_DIR = Path("skills/webnote-workflow/steps")
TEMPLATE_DIR = Path("runs/_template")
INVARIANTS_SOURCE = Path("docs/architecture.md")

# 技能入口：只有这四个 SKILL.md 参与路由（browser-skill 是外部副本，单独断言）
SKILLS = [
    "skills/webnote-workflow/SKILL.md",
    "skills/web-archive/SKILL.md",
    "skills/image-extract/SKILL.md",
    "skills/video-extract/SKILL.md",
]

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


def frontmatter(p: Path) -> dict:
    text = read(p)
    assert text.startswith("---\n"), f"{p.relative_to(ROOT).as_posix()} 缺 frontmatter"
    end = text.find("\n---", 3)
    assert end > 0, f"{p.relative_to(ROOT).as_posix()} frontmatter 未闭合"
    return yaml.safe_load(text[4:end]) or {}


def step_files() -> list[Path]:
    return sorted(p for p in (ROOT / STEPS_DIR).glob("0*.md"))


def test_skill_entries_present():
    missing, bad = [], []
    for rel in SKILLS:
        p = ROOT / rel
        if not p.is_file():
            missing.append(rel)
            continue
        head = read(p)[:1200]
        for field in ("name:", "description:"):
            if field not in head:
                bad.append(f"{rel} 缺 {field}")
    assert not missing, "技能入口缺失：\n" + "\n".join(missing)
    assert not bad, "frontmatter 不完整：\n" + "\n".join(bad)


def test_steps_are_the_only_pipeline():
    """流水线的唯一定义在 steps/：文件名即顺序，编号连续，没有第二份顺序表。"""
    files = step_files()
    names = [p.name for p in files]
    expected = ["00-collect.md", "01-classify.md", "02-distil.md", "03-verify.md", "04-confirm.md"]
    assert names == expected, f"步骤文件应恰好是 {expected}，实际 {names}"

    for i, p in enumerate(files, 1):
        fm = frontmatter(p)
        where = p.relative_to(ROOT).as_posix()
        assert fm.get("step") == i, f"{where} 的 step 应为 {i}，实际 {fm.get('step')}"
        assert fm.get("context") in {"none", "isolated", "fresh"}, f"{where} 的 context 取值非法：{fm.get('context')}"
        produces = fm.get("produces")
        assert produces, f"{where} 缺 produces"
        assert (ROOT / TEMPLATE_DIR / produces).is_file(), f"{where} 声明的产出 {produces} 在 runs/_template 里不存在"
        if fm.get("context") != "none":
            # 需要独立上下文的步骤必须声明可写范围
            writes = fm.get("writes") or []
            assert writes and all(str(w).startswith("runs/<run>/") for w in writes), (
                f"{where} 的 writes 必须全部落在 runs/<run>/ 内：{writes}"
            )


@pytest.mark.parametrize("path", step_files(), ids=lambda p: p.name)
def test_template_matches_step_card(path):
    """每份产出的表头由步骤文件的 format_needles 定义，模板必须一致。

    加字段时：改步骤文件的 format_needles + 改 runs/_template 对应文件，测试自动跟着走。
    """
    fm = frontmatter(path)
    needles = fm.get("format_needles") or []
    assert needles, f"{path.name} 没有 format_needles（产出格式无处定义）"
    src = read(path)
    tpl = read(ROOT / TEMPLATE_DIR / fm["produces"])
    for needle in needles:
        assert needle in src, f"{path.name} 自己缺 {needle!r}"
        assert needle in tpl, f"runs/_template/{fm['produces']} 缺 {needle!r}（规范改了，模板要一起改）"


def test_run_template_is_tracked_not_ignored():
    """骨架必须进 git：runs/* 的忽略规则不得把它吞掉。"""
    target = "runs/_template/00-采编清单.md"
    res = subprocess.run(["git", "check-ignore", target], cwd=ROOT, capture_output=True, text=True)
    assert res.returncode == 1, f"{target} 被 .gitignore 忽略了，需要 !runs/_template/** 例外"


def test_invariants_have_one_source():
    """三条铁律只在 docs/architecture.md 定义；别处只能引用，不能另写一版。

    历史上 `AGENTS.md` 与 `SKILL.md` 各写一版，第三条一版是「不改写用户已有文件」、
    另一版是「落地必待确认」，调度器与入口因此对「闸门是什么」答案不同。
    """
    src = read(ROOT / INVARIANTS_SOURCE)
    for phrase in ("正文不凭空编", "核查独立", "落地必待确认"):
        assert phrase in src, f"{INVARIANTS_SOURCE} 缺少铁律「{phrase}」"

    stale = "不改写用户已有文件"
    offenders = []
    for p in tracked_files():
        rel = p.relative_to(ROOT).as_posix()
        if rel.startswith(LEAK_EXEMPT_PREFIX) or rel.startswith("docs/history/"):
            continue
        if not p.is_file() or p.suffix not in {".md", ".py"}:
            continue
        if rel == INVARIANTS_SOURCE.as_posix():
            continue
        if stale in read(p):
            offenders.append(rel)
    assert not offenders, "「不改写用户已有文件」是废弃的铁律版本，仍在：\n" + "\n".join(offenders)


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
    """已退役的结构不得回来：旧的步骤卡目录、旧的角色目录、旧脚本目录。"""
    legacy = [
        "references/steps",
        "agents/classifier.md",
        "agents/distiller.md",
        "agents/verifier.md",
        "_agent_scripts",
        "Webpage note workflow.md",
    ]
    ext = {".md", ".py", ".ps1", ".yml", ".yaml", ".json", ".toml", ".cfg"}
    hits = []
    for p in tracked_files():
        rel = p.relative_to(ROOT).as_posix()
        # docs/decisions.md 是决策台账，按规矩原文不改，必然提到当时的结构
        if (rel.startswith(LEAK_EXEMPT_PREFIX) or rel.startswith(("tools/_migrations/", "docs/history/"))
                or rel == "docs/decisions.md"):
            continue
        if not p.is_file() or p.suffix not in ext:
            continue
        text = read(p)
        for pat in legacy:
            if pat in text:
                hits.append(f"{rel} 仍引用 {pat}")
    assert not hits, "旧结构残留：\n" + "\n".join(hits)


def test_vendored_skill_is_a_real_copy():
    """外部技能必须是真副本：真目录、无链接、只此一份，不经本地中转。"""
    vendored = ROOT / "skills/browser-skill"
    assert vendored.is_dir() and not vendored.is_symlink(), "skills/browser-skill 必须是真实目录"
    assert not any(p.is_symlink() for p in vendored.rglob("*")), "副本里不该有符号链接"
    assert "name: browser-skill" in read(vendored / "SKILL.md")[:400], "副本缺 frontmatter 或名字不对"
    assert not (ROOT / ".skillshare").exists(), "真源记在 bot.yaml，不要再加一份本地中转声明（见 docs/decisions.md）"


def test_vendored_manifest_records_upstream():
    """外部技能的真源必须记在 bot.yaml：上游仓库 + 具体 commit + 快照日期。"""
    bot = yaml.safe_load((ROOT / "bot.yaml").read_text(encoding="utf-8")) or {}
    entries = bot.get("vendored") or []
    assert entries, "bot.yaml 缺 vendored 段（外部技能的来源声明）"

    for v in entries:
        where = f"vendored: {v.get('path')}"
        assert v["upstream"].startswith("https://github.com/"), f"{where} 的 upstream 必须是仓库地址"
        assert re.fullmatch(r"[0-9a-f]{40}", str(v["ref"])), f"{where} 的 ref 必须是完整 commit sha"
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(v["snapshot"])), f"{where} 的 snapshot 必须是日期"

        path = ROOT / v["path"]
        assert path.is_dir(), f"{where} 副本目录不存在"
        assert not any(p.is_symlink() for p in path.rglob("*")), f"{where} 里不该有符号链接"
        actual = len([p for p in path.rglob("*") if p.is_file()])
        assert v.get("files") == actual, f"{where} 记了 {v.get('files')} 个文件，实际 {actual}（跑 --pull 修）"


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
