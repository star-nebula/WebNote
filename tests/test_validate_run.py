"""校验器自己的测试：先证明它认得出好产物，再证明它抓得住每一类真错。

工具 `tools/validate_run.py` 是生产线的一部分（每份提案写完就该跑），
所以它必须有一个「注入坏数据 → 必须报出来」的测试；
否则它退化成一个永远说 OK 的装饰品。
"""

from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_validator():
    spec = importlib.util.spec_from_file_location("validate_run", ROOT / "tools" / "validate_run.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["validate_run"] = mod  # dataclass 解析注解时要能查到本模块
    spec.loader.exec_module(mod)
    return mod


V = load_validator()

SAMPLE = {
    "00-采编清单.md": textwrap.dedent(
        """\
        # 00-采编清单

        > 生成时间：2026-11-11
        > 执行者：调度器（主会话）
        > 运行模式：模式 A
        > 输入批次：2 条
        > 输出目录：`runs/2026-11-11-样例/`

        ## 内容清单

        | ID | 标题 | 域名 | 媒体格式 | 正文字符数 | 有正文 | 提取方式 | 提取结果 | 原文来源 |
        |----|------|------|---------|-----------|--------|---------|---------|---------|
        | p01 | 甲 | example.com | 图文 | 1200 | 有 | 网页直取 | 成功 | `原文/p01.txt` |
        | p02 | 乙 | example.com | 图文 | 90 | 有（疑截断） | 网页直取 | 成功 | `原文/p02.txt` |
        | p03 | 丙 | example.com | 视频 | 0 | 无 | ASR | 失败 | `原文/p03.txt` |

        ## 有正文统计（供 01-笔记 使用）

        - 有正文：1 条
        - 有（疑截断）：1 条
        - 无正文：1 条

        ## 运行异常

        - 无
        """
    ),
    "01-笔记.md": textwrap.dedent(
        """\
        # 01-笔记

        ## p01 · 甲
        **媒体**：图文 · **来源类型**：原文

        1. 甲的第一条要点（出处：第 2 段 · 原文）
        2. 甲的第二条要点（出处：第 4 段 · 原文）

        **为什么值得保留**：讲清了机制
        **修订建议**：值得深读

        ## p02 · 乙
        **媒体**：图文 · **来源类型**：OCR

        1. 乙的要点（出处：第 3 段 · OCR）

        **为什么值得保留**：只在残片里出现过
        **修订建议**：补充数据
        """
    ),
    "02-核查表.md": textwrap.dedent(
        """\
        # 02-核查表

        > 生成时间：2026-11-11
        > 执行者：核查官（全新上下文，与笔记匠独立）
        > 汇总：共 3 条 · 直接引用 2 · 转述源 1 · 可疑 0

        ## p01 · 甲

        | 条目 | 要点 | 状态 | 来源类型 | 正文依据 |
        |------|------|------|---------|---------|
        | p01-1 | 甲的第一条要点 | 已核实（直接引用） | 原文 | 第 2 段逐句对应 |
        | p01-2 | 甲的第二条要点 | 已核实（直接引用） | 原文 | 第 4 段逐句对应 |

        ## p02 · 乙

        | 条目 | 要点 | 状态 | 来源类型 | 正文依据 |
        |------|------|------|---------|---------|
        | p02-1 | 乙的要点 | 已核实（转述源） | OCR | 残片 t=205s 帧 |

        ## 需用户回看的条目

        | 条目 | 状态 | 为什么需要回看 |
        |------|------|--------------|
        | p02-1 | 已核实（转述源） | 残片含识别噪声，需核对原始画面 |
        """
    ),
    "03-待确认提案.md": textwrap.dedent(
        """\
        # 03-待确认提案

        > 生成时间：2026-11-11
        > 状态：**全部待确认，未执行任何落地动作**

        ## 汇总

        | 状态 | 条数 |
        |---|---|
        | 已核实（直接引用） | 2 |
        | 已核实（转述源） | 1 |
        | 可疑 | 0 |

        ## 一、去向（按页）

        | 页 | 标题 | 建议去向 | 依据 |
        |---|---|---|---|
        | p01 | 甲 | 人工智能 | 讲的是模型 |
        | p02 | 乙 | 待定 · 需你定类目 | 残片，类目不好定 |

        ## 二、建议保留

        | 条目 | 建议动作 | 依据 |
        |---|---|---|
        | p01-1 | 保留 | 值得深读 |
        | p01-2 | 保留 | 值得深读 |

        ## 三、建议保留但需你回看（转述源）

        | 条目 | 为什么需要回看 | 建议动作 |
        |---|---|---|
        | p02-1 | 残片含误识别 | 补充数据后再存 |

        ## 四、建议修正或删除

        | 条目 | 问题 | 建议动作 |
        |---|---|---|

        ## 待你确认的落地动作

        - [ ] 把 p01 写入人工智能类目
        - [ ] 回看 p02 的残片后决定
        """
    ),
}


def make_run(tmp_path: Path, edits: dict[str, str] | None = None, drop: tuple[str, ...] = ()) -> Path:
    run = tmp_path / "2026-11-11-样例"
    run.mkdir()
    for name, body in SAMPLE.items():
        if name in drop:
            continue
        if edits and name in edits:
            body = edits[name]
        (run / name).write_text(body, encoding="utf-8")
    return run


def codes(run: Path) -> set[str]:
    rep = V.validate(run)
    return {issue.code for issue in rep.issues}


def test_sample_is_clean(tmp_path):
    rep = V.validate(make_run(tmp_path))
    assert rep.errors == [], [i.render() for i in rep.issues]


def test_clean_sample_exits_zero(tmp_path, capsys):
    run = make_run(tmp_path)
    assert V.main([str(run)]) == 0
    assert "OK" in capsys.readouterr().out


# ---- 注入五类真错：每一类都必须被指出来 ----


def test_missing_artifact(tmp_path):
    run = make_run(tmp_path, drop=("03-待确认提案.md",))
    assert "E_MISSING_FILE" in codes(run)


def test_summary_count_drift(tmp_path):
    """核查表汇总写 4 条、表里 3 条——真实发生过（人眼发现）。"""
    body = SAMPLE["02-核查表.md"].replace("共 3 条", "共 4 条")
    assert "E_COUNT_TOTAL" in codes(make_run(tmp_path, {"02-核查表.md": body}))


def test_broken_entry_numbering(tmp_path):
    """删掉 p01-2 却没补号，提案会指向不存在的条目。"""
    body = SAMPLE["02-核查表.md"].replace("| p01-2 |", "| p01-9 |").replace(
        "直接引用 2", "直接引用 2"
    )
    run = make_run(tmp_path, {"02-核查表.md": body})
    assert "E_ENTRY_ID_SEQ" in codes(run)


def test_transitive_source_promoted_to_direct_quote(tmp_path):
    """把 OCR 的结论标成「直接引用」= 把转述源升格。"""
    body = SAMPLE["02-核查表.md"].replace(
        "| p02-1 | 乙的要点 | 已核实（转述源） | OCR |", "| p02-1 | 乙的要点 | 已核实（直接引用） | OCR |"
    )
    assert "E_STATE_SOURCE_MISMATCH" in codes(make_run(tmp_path, {"02-核查表.md": body}))


def test_note_without_citation(tmp_path):
    body = SAMPLE["01-笔记.md"].replace("（出处：第 4 段 · 原文）", "")
    assert "E_NO_CITATION" in codes(make_run(tmp_path, {"01-笔记.md": body}))


def test_proposal_drops_an_entry(tmp_path):
    body = SAMPLE["03-待确认提案.md"].replace("| p01-2 | 保留 | 值得深读 |\n", "")
    assert "E_UNCOVERED_ENTRY" in codes(make_run(tmp_path, {"03-待确认提案.md": body}))


def test_proposal_entry_listed_twice(tmp_path):
    body = SAMPLE["03-待确认提案.md"].replace(
        "| 条目 | 问题 | 建议动作 |\n|---|---|---|\n",
        "| 条目 | 问题 | 建议动作 |\n|---|---|---|\n| p01-1 | 重复出现 | 删除 |\n",
    )
    assert "E_DUPLICATE_ENTRY" in codes(make_run(tmp_path, {"03-待确认提案.md": body}))


def test_proposal_missing_destination_for_a_page(tmp_path):
    body = SAMPLE["03-待确认提案.md"].replace(
        "| p02 | 乙 | 待定 · 需你定类目 | 残片，类目不好定 |\n", ""
    )
    assert "E_DEST_PAGES" in codes(make_run(tmp_path, {"03-待确认提案.md": body}))


def test_body_stats_drift(tmp_path):
    body = SAMPLE["00-采编清单.md"].replace("- 有正文：1 条", "- 有正文：2 条")
    assert "E_STATS_MISMATCH" in codes(make_run(tmp_path, {"00-采编清单.md": body}))


def test_citation_source_disagrees_with_verdict(tmp_path):
    """笔记说这段是原文，核查官说它是 OCR——同一句话两个来源。"""
    body = SAMPLE["01-笔记.md"].replace("（出处：第 3 段 · OCR）", "（出处：第 3 段 · 原文）")
    assert "E_QUOTE_SOURCE_MISMATCH" in codes(make_run(tmp_path, {"01-笔记.md": body}))


def test_unknown_state_word(tmp_path):
    body = SAMPLE["02-核查表.md"].replace("已核实（转述源） | OCR", "已验证 | OCR")
    assert "E_STATE_INVALID" in codes(make_run(tmp_path, {"02-核查表.md": body}))


def test_missing_file_is_reported_once_not_crashed(tmp_path):
    run = make_run(tmp_path, drop=("01-笔记.md",))
    rep = V.validate(run)
    assert any(i.code == "E_MISSING_FILE" for i in rep.issues)


def test_legacy_five_file_runs_are_skipped(tmp_path):
    """旧版五文件结构是存档：--all 要跳过它，而不是让钩子永远红。"""
    runs = tmp_path / "runs"
    legacy = runs / "2026-09-03-端到端验收"
    legacy.mkdir(parents=True)
    (legacy / "02-笔记.md").write_text("旧结构", encoding="utf-8")

    current = runs / "2026-11-11-新的"
    current.mkdir()
    (current / "01-笔记.md").write_text("新结构", encoding="utf-8")

    got_current, got_legacy = V.find_runs(tmp_path)
    assert [p.name for p in got_current] == ["2026-11-11-新的"]
    assert [p.name for p in got_legacy] == ["2026-09-03-端到端验收"]


def test_validator_is_wired_into_the_pipeline():
    """校验器不能只活在测试里——入口自检与 pre-push 钩子都要真的调用它。"""
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    hook = (ROOT / ".githooks" / "pre-push").read_text(encoding="utf-8")
    confirm = (ROOT / "skills/webnote-workflow/steps/03-confirm.md").read_text(encoding="utf-8")
    assert "tools/validate_run.py" in agents, "AGENTS.md 的自检命令里没有校验器"
    assert "validate_run" in hook, "pre-push 没有跑校验器"
    assert "validate_run" in confirm, "确认步没要求写完后校验"
