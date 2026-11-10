"""仓库不变量：CI 与本地跑同一套。

跑法：python -m pytest tests -q

只断言「改了会静默变坏」的东西：
  - 入口与私有叠加层各归其位（AGENTS.md 进 git，AGENTS.local.md 不进）
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
    assert len(needles) == len(set(needles)), f"{path.name} 的 format_needles 有重复项"
    tpl = read(ROOT / TEMPLATE_DIR / fm["produces"])
    for needle in needles:
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


def test_no_private_path_leak():
    hits = []
    for p in tracked_files():
        rel = p.relative_to(ROOT).as_posix()
        if rel.startswith(LEAK_EXEMPT_PREFIX):
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


def test_role_names_have_one_wording():
    """每个步骤里的 role 必须在 AGENTS.md 里以同一个词出现。

    曾经同一个角色有三种叫法：契约里 `classifier`、流水线表里「归类师」、
    步骤文件里「内容分类员」——读的人得先猜它们是不是同一个。
    """
    agents = read(ROOT / "AGENTS.md")
    missing = [
        f"{p.name}: role={frontmatter(p).get('role')!r}"
        for p in step_files()
        if frontmatter(p).get("role") and frontmatter(p)["role"] not in agents
    ]
    assert not missing, "AGENTS.md 里的角色名与步骤文件不一致：\n" + "\n".join(missing)


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


def test_steps_declare_boundaries():
    """每个步骤文件都要声明读什么、不许做什么；写下的仓库路径必须真的存在。

    曾经只有 01–03 有 reads/forbidden，00 与 04 空着——契约表看着齐，实际缺一半。
    """
    never = ["00-collect.md", "01-classify.md", "02-distil.md", "03-verify.md", "04-confirm.md"]
    problems = []
    for name in never:
        fm = frontmatter(ROOT / STEPS_DIR / name)
        for key in ("reads", "forbidden", "writes"):
            if not fm.get(key):
                problems.append(f"{name} 缺 {key}")
        for item in fm.get("reads") or []:
            item = str(item)
            if item.startswith(("skills/", "docs/", "tools/")):
                if not (ROOT / item).exists():
                    problems.append(f"{name} 的 reads 指向不存在的路径：{item}")
            elif item.startswith("runs/<run>/"):
                if not (ROOT / TEMPLATE_DIR / Path(item).name).is_file():
                    problems.append(f"{name} 的 reads 读不到对应产出：{item}")
    assert not problems, "步骤契约不完整：\n" + "\n".join(problems)


def test_branches_are_ordered_and_reachable():
    """采编分支卡靠 branch_of + order 排序，且必须从 00 指得到——否则是一堆孤儿文件。"""
    branches = sorted((ROOT / STEPS_DIR / "branches").glob("*.md"))
    assert branches, "steps/branches/ 为空"
    orders = []
    src = read(ROOT / STEPS_DIR / "00-collect.md")
    for p in branches:
        fm = frontmatter(p)
        where = p.relative_to(ROOT).as_posix()
        assert fm.get("branch_of") == "00-collect", f"{where} 的 branch_of 必须指向 00-collect"
        assert isinstance(fm.get("order"), int), f"{where} 缺整数 order"
        orders.append(fm["order"])
        assert p.name in src, f"00-collect.md 没有指向分支卡 {p.name}（孤儿）"
    assert orders == list(range(1, len(branches) + 1)), f"分支 order 应为 1..{len(branches)}，实际 {orders}"


def test_vendored_generation_lives_in_one_place():
    """上游代际只记在 bot.yaml。文档里再抄一份 commit sha，就一定会过期（已经发生过一次）。"""
    hits = []
    for p in tracked_files():
        rel = p.relative_to(ROOT).as_posix()
        if p.suffix != ".md" or rel in {"bot.yaml", "docs/decisions.md"}:
            continue
        if rel.startswith(("docs/history/", "docs/versions/", "tools/_migrations/")):
            continue
        for m in re.findall(r"\b[0-9a-f]{40}\b", read(p)):
            hits.append(f"{rel}: {m[:12]}…")
    assert not hits, "上游代际只能写在 bot.yaml：\n" + "\n".join(hits)


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


def test_entry_is_public_and_overlay_stays_private():
    """公开的必须是 AGENTS.md（工具按这个名字加载）；本机事实进 AGENTS.local.md 且不进 git。"""
    tracked = {q.relative_to(ROOT).as_posix() for q in tracked_files()}
    assert "AGENTS.md" in tracked, "AGENTS.md 必须被跟踪——各工具只认这个名字"
    assert "AGENTS.local.md" not in tracked, "AGENTS.local.md 是本机叠加层，不许进 git"
    overlay = ROOT / "AGENTS.local.md"
    if overlay.exists():
        r = subprocess.run(["git", "check-ignore", "-q", "AGENTS.local.md"], cwd=ROOT)
        assert r.returncode == 0, "AGENTS.local.md 必须被 .gitignore 忽略"
    # 叠加层只放私有内容：不许与入口出现同名「## 」小节（那是第二份契约的起点）
    if overlay.exists():
        headings = lambda t: {ln.strip() for ln in t.splitlines() if ln.startswith("## ")}
        clash = headings(read(ROOT / "AGENTS.md")) & headings(read(overlay))
        assert not clash, f"AGENTS.local.md 不该复述入口的小节：{sorted(clash)}"

# 台账与存档按规矩保留原样，其中的旧路径是历史事实
DOC_PATH_EXEMPT = ("docs/decisions.md", "docs/history/", "docs/versions/", "tools/_migrations/")


def test_documented_paths_exist():
    """活文档里用反引号写的仓库路径必须存在。

    2026-11-10 手工核过一次：除了台账与存档，其余都成立——但那是人肉查的，
    目录一旦上移（`tests/fixtures` → `tests/manual/fixtures`）就会静默指错。
    """
    pat = re.compile(r"`((?:skills|tools|tests|docs|runs)/[^`\s]*)`")
    hits = []
    for p in tracked_files():
        rel = p.relative_to(ROOT).as_posix()
        if p.suffix != ".md" or rel.startswith(DOC_PATH_EXEMPT):
            continue
        for token in pat.findall(read(p)):
            cand = token.rstrip("/")
            if any(ch in cand for ch in "*<>{}"):
                continue
            if not (ROOT / cand).exists():
                hits.append(f"{rel}: {cand}")
    assert not hits, "文档提到不存在的路径：\n" + "\n".join(sorted(set(hits)))


def test_manual_harness_paths_resolve():
    """`tests/manual/` 的 PowerShell 回归靠 `$PSScriptRoot` 反推仓库根；上移一层就会全指错。

    它不进 CI（要真浏览器），所以路径错了没人会红——只能靠静态断言兜住。
    """
    ps1 = ROOT / "tests/manual/test-web-archive.ps1"
    text = read(ps1)
    assert "$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)" in text, \
        "harness 在 tests/manual/ 下，仓库根要往上两级"
    assert (ROOT / "skills/web-archive/scripts/harvest.ps1").is_file()

    fixtures = ROOT / "tests/manual/fixtures"
    used = set(re.findall(r"File\s*=\s*'([^']+\.html)'", text))
    used |= set(re.findall(r"Join-Path \$fixtures '([^']+\.html)'", text))
    assert used, "没解析到任何夹具引用（正则失效？）"
    missing = sorted(n for n in used if not (fixtures / n).is_file())
    assert not missing, f"harness 引用了不存在的夹具：{missing}"

    present = {p.name for p in fixtures.glob("*.html")}
    assert not (present - used), f"夹具存在但没被任何用例引用：{sorted(present - used)}"


def test_documented_env_keys_are_read():
    """README 环境变量表里列出的键，必须有代码真的读它。

    `.env.example` 曾经列了 7 个键，其中 4 个代码从不读取，还有 1 个属于已删功能——
    承诺存在的开关比没有开关更糟。
    """
    keys = set(re.findall(r"^\| `([A-Z_][A-Z0-9_]*)` \|", read(ROOT / "README.md"), re.M))
    assert keys, "README 里没找到环境变量表"
    code = "\n".join(read(p) for p in tracked_files() if p.suffix in {".py", ".ps1"})
    missing = sorted(k for k in keys if k not in code)
    assert not missing, f"README 承诺这些环境变量有效，但没有代码读取：{missing}"
