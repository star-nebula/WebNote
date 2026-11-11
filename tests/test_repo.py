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

import json
import os
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
    expected = ["00-collect.md", "01-distil.md", "02-verify.md", "03-confirm.md"]
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


def test_taxonomy_is_user_owned():
    """分类类目归用户，不归本仓。

    每个用户对网页内容的分类体系都不同。曾经有一个独立的「归类师」步骤，
    强制四选一（学习/借鉴/内容补充/可归档）——用户有自己的体系时它要么打架、
    要么被忽略，而它的产出没有任何下游消费者。现在只在 03-confirm 里做去向建议，
    且必须优先用用户自己的体系；四类只做兜底。
    """
    fallback = ["学习", "借鉴", "内容补充", "可归档"]
    offenders = []
    for p in step_files():
        text = read(p)
        if p.name == "03-confirm.md":
            continue
        hit = [w for w in fallback if f"| {w} |" in text or f"**{w}**" in text]
        if hit:
            offenders.append(f"{p.name}: {hit}")
    assert not offenders, "分类类目只该作为兜底出现在 03-confirm.md：\n" + "\n".join(offenders)

    confirm = read(ROOT / STEPS_DIR / "03-confirm.md")
    assert "AGENTS.local.md" in confirm, "03-confirm.md 必须先读用户的分类体系（AGENTS.local.md）"
    assert "兜底" in confirm, "03-confirm.md 必须写明兜底条件"


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
    never = ["00-collect.md", "01-distil.md", "02-verify.md", "03-confirm.md"]
    problems = []
    for name in never:
        fm = frontmatter(ROOT / STEPS_DIR / name)
        for key in ("reads", "forbidden", "writes"):
            if not fm.get(key):
                problems.append(f"{name} 缺 {key}")
        for item in fm.get("reads") or []:
            # reads 允许带括注说明用途（如「仅回修模式」），校验时去掉
            item = re.sub(r"（[^）]*）$", "", str(item)).strip()
            if item.startswith(("skills/", "docs/", "tools/")):
                if not (ROOT / item).exists():
                    problems.append(f"{name} 的 reads 指向不存在的路径：{item}")
            elif item.startswith("runs/<run>/原文/"):
                continue  # 运行期生成的正文副本，模板里没有对应文件
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


def test_body_threshold_is_owned_by_the_step():
    """「有正文」的判据必须写在 00-collect 里，不能只活在口头。

    它曾经写在别处，删那一步时一起丢了，于是写这一列的人临场定、读这一列的人当事实。
    """
    collect = read(ROOT / STEPS_DIR / "00-collect.md")
    assert "有（疑截断）" in collect, "00-collect.md 必须定义「有（疑截断）」这一档"
    assert "200" in collect and "50" in collect, "00-collect.md 必须给出两档阈值"
    for name in ("01-distil.md", "02-verify.md"):
        assert "疑截断" in read(ROOT / STEPS_DIR / name), f"{name} 没接住「有（疑截断）」这条规则"


def test_value_signal_reaches_confirmation():
    """笔记匠给的价值信号（修订建议）必须在确认步被使用。

    核查只管真假；没有这条线，确认步只能按真假分堆，"根本不值得留"无法表达。
    """
    confirm = read(ROOT / STEPS_DIR / "03-confirm.md")
    assert "修订建议" in confirm, "03-confirm.md 没有使用 01-笔记 的修订建议"
    assert "可忽略" in confirm, "03-confirm.md 必须写明「可忽略 → 不落库」"


def test_rework_path_is_defined():
    """可疑条目要有回修路径，否则三态判定止于贴标签。"""
    distil = read(ROOT / STEPS_DIR / "01-distil.md")
    confirm = read(ROOT / STEPS_DIR / "03-confirm.md")
    assert "回修" in distil, "01-distil.md 缺「回修模式」"
    assert "不许新增条目" in distil, "回修必须禁止新增条目（新增等于绕过核查）"
    assert "最多回修两次" in confirm, "03-confirm.md 必须写明回修次数上限"


def test_original_text_copy_is_source_of_truth():
    """采编必须留正文副本，提炼与核查只读它。

    网页是活的：改版、付费墙收紧、登录态过期都会让核查官看到与笔记匠不同的东西，
    那时判「可疑」删掉的是无辜条目。
    """
    collect = read(ROOT / STEPS_DIR / "00-collect.md")
    assert "原文/<ID>.txt" in collect, "00-collect.md 必须规定把正文落到 runs/<run>/原文/<ID>.txt"
    for name in ("01-distil.md", "02-verify.md"):
        step = read(ROOT / STEPS_DIR / name)
        assert "原文/<ID>.txt" in step, f"{name} 的 reads 必须指向正文副本"
    assert "不要去重抓" in read(ROOT / STEPS_DIR / "01-distil.md"), "01-distil.md 必须禁止重抓网页"


def test_naming_defaults_to_the_title():
    """默认用原标题；作者/平台只在重名时才加，且重名不许停下来问。"""
    confirm = read(ROOT / STEPS_DIR / "03-confirm.md")
    assert "直接用原标题" in confirm, "03-confirm.md 必须规定默认用原标题命名"
    assert "重名" in confirm, "03-confirm.md 必须说明只有重名时才追加作者与平台"
    assert "重名不停下来问用户" in confirm, "重名应自动升级命名，不许再用提问阻塞"
    assert "三者缺一不可" not in confirm, "旧的「标题-作者-平台 三者缺一不可」规则应已废止"


def test_entry_leaks_no_downstream_intent():
    """入口只说到 runs/ 为止：出现落库目录名，等于把"之后要做什么"写进公开文件。"""
    entry = read(ROOT / "AGENTS.md")
    for kw in ("Resources", "Knowledge", "落库"):
        assert kw not in entry, f"AGENTS.md 不该出现下游意图：{kw}（这些归 AGENTS.local.md）"


def test_post_runs_rules_live_in_the_overlay():
    """入口只记到 runs/ 为止；落库命名与 Knowledge 原子化属于 runs 之后，写进叠加层。"""
    confirm = read(ROOT / STEPS_DIR / "03-confirm.md")
    entry = read(ROOT / "AGENTS.md")
    assert "AGENTS.local.md" in confirm, "03-confirm.md 必须把 runs 之后的约定指给 AGENTS.local.md"
    assert "AGENTS.local.md" in entry, "AGENTS.md 必须说明 runs 之后的约定在叠加层"
    assert "只负责到" in entry and "runs/" in entry, \
        "AGENTS.md 必须写明本仓只负责到 runs/ 为止"


def test_run_archive_dir_is_tracked():
    """跑完的 run 要有去处，否则只有占位没有归档习惯。"""
    placeholder = ROOT / "runs/_archive/.gitkeep"
    assert placeholder.exists(), "runs/_archive/ 不存在"
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "runs/_archive/.gitkeep"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert tracked.returncode == 0, "runs/_archive/.gitkeep 未被 git 跟踪"


def test_entry_ids_have_one_format():
    """条目号必须是 p<页>-<序>，全链一套。

    曾经三态表用「1. 摘要」、回看表用「p06-1」，而回修规则要求引用「条目号」——
    两套编号并存，锚点指向不明，且摘要一改锚点就断。
    """
    verify = read(ROOT / STEPS_DIR / "02-verify.md")
    confirm = read(ROOT / STEPS_DIR / "03-confirm.md")
    template = read(ROOT / TEMPLATE_DIR / "02-核查表.md")
    assert "p<页>-<序>" in verify, "02-verify.md 必须写出条目号规则"
    assert "p<页>-<序>" in confirm, "03-confirm.md 必须声明沿用核查表的条目号"
    assert "p01-1" in template, "02-核查表 模板的条目列必须用 p01-1 这种 ID"
    assert "| 1. <要点摘要>" not in template, "模板里不该再出现「1. 摘要」这种编号"


# ---- 提取类工具的输出契约 ----
# 00-collect.md 规定所有提取工具在 stdout 输出同一份 JSON；这里钉住失败分支。
EXTRACTOR_CONTRACT = {"success", "text", "char_count", "method", "error"}
EXTRACTOR_CASES = {
    "extract-document.py": ["/nope/missing.pdf"],
    "extract-image-ocr.py": ["--input", "/nope/missing.png"],
    "extract-video-asr.py": ["/nope/missing.mp4"],
    "extract-video-frames.py": ["--input", "/nope/missing.mp4"],
    "extract-video-text.py": ["/nope/missing.mp4"],
    "extract-webpage.py": ["file:///nope/missing.html"],
    "ds_vision.py": ["/nope/missing.png"],
}


# 走浏览器（bsk）的工具在"bsk 已装但 daemon 起不来"的机器上会挂住几十秒。
# 契约测的是失败分支，把外部可执行文件从 PATH 里摘掉反而是最具决定性的一种失败。
NO_EXTERNAL_BIN = {"extract-webpage.py", "extract-video-text.py"}


@pytest.mark.parametrize("name", sorted(EXTRACTOR_CASES))
def test_extractor_failure_json_contract(name, tmp_path):
    """提取工具失败时也必须吐出五个键，而不是散文或空输出。

    调用方（调度器）靠 success/method 决定下一步；格式一飘，采编清单的
    「提取结果」列就写不出可判读的东西。
    """
    env = None
    if name in NO_EXTERNAL_BIN:
        empty_bin = tmp_path / "empty-bin"
        empty_bin.mkdir()
        env = {**os.environ, "PATH": str(empty_bin)}
    r = subprocess.run(
        [sys.executable, str(ROOT / "tools" / name), *EXTRACTOR_CASES[name]],
        cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace", timeout=120,
        env=env,
    )
    lines = [ln for ln in (r.stdout or "").splitlines() if ln.lstrip().startswith("{")]
    assert lines, f"{name} 失败时没有输出 JSON：{(r.stdout or '')[-400:]}{(r.stderr or '')[-400:]}"
    payload = json.loads(lines[-1])
    assert set(payload) == EXTRACTOR_CONTRACT, f"{name} 输出的键不对：{sorted(payload)}"
    assert payload["success"] is False, f"{name} 对不存在的输入应报 success=false"
    assert payload["method"] == "error", f"{name} 失败时 method 应为 error"
    assert isinstance(payload["char_count"], int) and payload["char_count"] == 0
    assert isinstance(payload["error"], str) and payload["error"], f"{name} 失败时必须给出原因"


def test_every_extractor_is_covered_by_contract():
    """新增提取工具必须同时补上契约用例，否则这条断言形同虚设。"""
    on_disk = {p.name for p in (ROOT / "tools").glob("extract-*.py")} | {"ds_vision.py"}
    missing = on_disk - set(EXTRACTOR_CASES)
    assert not missing, f"这些工具没有输出契约用例：{sorted(missing)}"


def test_core_task_and_boundaries_are_stated():
    """入口里必须有"不做什么"——否则每个新需求都会被当成该做。"""
    entry = read(ROOT / "AGENTS.md")
    for kw in ("这个 bot 的任务", "转存", "可核查", "它不负责"):
        assert kw in entry, f"AGENTS.md 缺核心任务段的关键词：{kw}"
    assert "对\"内容说了什么\"负责" in entry or "对“内容说了什么”负责" in entry, \
        "AGENTS.md 缺那句一句话定位"


def test_collect_dedupes_before_extracting():
    """采编第一步是查重，不是提取。同一链接进两次会产出两份互相矛盾的笔记。"""
    collect = read(ROOT / STEPS_DIR / "00-collect.md")
    assert "先查重" in collect, "00-collect.md 缺查重步骤"
    for kw in ("重采", "跳过", "只更新"):
        assert kw in collect, f"查重命中后的三个选项缺 {kw}"
    assert "已采过：" in collect, "00-collect.md 必须要求在清单里留「已采过」痕迹"
