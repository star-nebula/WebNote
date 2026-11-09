"""仓库不变量测试：CI 与本地跑同一套。

跑法：python -m pytest tests -q
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ["webnote-workflow", "web-archive", "image-extract", "video-extract", "xhs-note"]
STEPS = ["collect.md", "collect-image.md", "collect-video-audio.md", "collect-web-archive.md", "confirm.md"]
AGENTS = ["classifier.md", "distiller.md", "verifier.md"]

# 私有路径 / 身份指纹：出现在被 git 跟踪的文件里就是泄漏
LEAK_PATTERNS = [
    r"[A-Za-z]:\\knowledge",
    r"[A-Za-z]:\\Projects\\Github",
    r"[A-Za-z]:\\Users\\[A-Za-z0-9_.-]+",
    r"\bHermes\b",
]
# 历史快照与测试自身可以出现旧路径
LEAK_EXEMPT_PREFIX = ("tests/", "docs/versions/")
BINARY_SUFFIX = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".wav", ".pdf", ".ico"}


def tracked_files():
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    return [ROOT / p.decode("utf-8") for p in out.split(b"\0") if p]


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="ignore")


@pytest.mark.parametrize("name", SKILLS)
def test_skill_has_frontmatter(name: str):
    skill = ROOT / "skills" / name / "SKILL.md"
    assert skill.is_file(), f"缺 skills/{name}/SKILL.md"
    head = read(skill)[:800]
    assert head.startswith("---"), f"skills/{name}/SKILL.md 必须带 frontmatter"
    assert re.search(r"^name:\s*\S+", head, re.M), f"skills/{name}/SKILL.md 缺 name"
    assert re.search(r"^description:\s*\S+", head, re.M), f"skills/{name}/SKILL.md 缺 description"


@pytest.mark.parametrize("name", STEPS)
def test_step_card_exists(name: str):
    p = ROOT / "skills" / "webnote-workflow" / "references" / "steps" / name
    assert p.is_file(), f"缺流程细则 {p.relative_to(ROOT)}"


@pytest.mark.parametrize("name", AGENTS)
def test_agent_definition_exists(name: str):
    p = ROOT / "agents" / name
    assert p.is_file(), f"缺角色定义 agents/{name}"
    assert "context:" in read(p)[:1200], f"agents/{name} 缺 frontmatter 契约 context"


def test_public_agents_in_sync():
    if not (ROOT / "AGENTS.md").is_file():
        pytest.skip("本地没有私有 AGENTS.md（公开克隆），跳过")
    gen = ROOT / "tools" / "sync-agents-public.py"
    r = subprocess.run([sys.executable, str(gen), "--check"], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, (r.stdout + r.stderr).strip()


def test_no_private_path_leak():
    hits = []
    for p in tracked_files():
        rel = p.relative_to(ROOT).as_posix()
        if rel.startswith(LEAK_EXEMPT_PREFIX) or rel == "tools/sync-agents-public.py" or not p.is_file() or p.suffix in BINARY_SUFFIX:
            continue
        for i, line in enumerate(read(p).splitlines(), 1):
            for pat in LEAK_PATTERNS:
                if re.search(pat, line):
                    hits.append(f"{rel}:{i}: {line.strip()[:90]}")
    assert not hits, "私有路径 / 身份泄漏：\n" + "\n".join(hits)


def test_private_entry_not_tracked():
    files = set(subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.splitlines())
    assert "AGENTS.md" not in files, "私有 AGENTS.md 不能进 git"
    assert "AGENTS.public.md" in files, "公开版 AGENTS.public.md 必须在 git 里"
    assert not [f for f in files if f.startswith("persona/")], "persona/ 是私有目录，不能进 git"


def test_no_legacy_paths():
    legacy = ["_agent_scripts", "Webpage note workflow.md"]
    ext = {".md", ".py", ".ps1", ".yml", ".yaml", ".json", ".toml", ".cfg"}
    hits = []
    for p in tracked_files():
        rel = p.relative_to(ROOT).as_posix()
        if rel.startswith(LEAK_EXEMPT_PREFIX) or rel.startswith("tools/_migrations/") or not p.is_file():
            continue
        if p.suffix not in ext:
            continue
        text = read(p)
        for pat in legacy:
            if pat in text:
                hits.append(f"{rel} 仍引用旧路径 {pat}")
    assert not hits, "旧路径残留：\n" + "\n".join(hits)
