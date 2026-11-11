#!/usr/bin/env python3
"""
校验一份 run 的四份产物是否自洽。

四步流水线里，01 提炼与 02 核查由 AI 执行，内容对不对机器判断不了；
但「这一步交出的东西，下一步能不能用」是能判断的——条数是否对得上、
条目号是否连续、三态与来源类型的组合是否合法、提案里的每条是否都有出处。
本工具只查这些结构事实，不查内容真假。

用法：
  python tools/validate_run.py runs/2026-11-11-某主题/
  python tools/validate_run.py --all            # 扫 runs/ 下所有 run（跳过 _template）
  python tools/validate_run.py runs/xxx/ --json

退出码：0 = 无 ERROR（可能有 WARN）；1 = 至少一条 ERROR；2 = 目录不成立。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

STATES = ("已核实（直接引用）", "已核实（转述源）", "可疑")
TRANSITIVE_SOURCES = ("OCR", "ASR", "Vision")
SOURCES = ("原文",) + TRANSITIVE_SOURCES
BODY_STATES = ("有", "有（疑截断）", "无")
ADVICE = ("值得深读", "可忽略", "补充数据", "参考写法")
REQUIRED_FILES = (
    "00-采编清单.md",
    "01-笔记.md",
    "02-核查表.md",
    "03-待确认提案.md",
)

PAGE_RE = re.compile(r"^##\s+(p\d{2})\s*·\s*(.+?)\s*$")
ENTRY_ID_RE = re.compile(r"^(p\d{2})-(\d+)$")
CITE_RE = re.compile(r"（出处：([^）]*?)·\s*(原文|OCR|ASR|Vision)\s*）")
ANY_CITE_RE = re.compile(r"（出处：")
NUM_ITEM_RE = re.compile(r"^\s*\d+\.\s+(.*)$")


@dataclass
class Issue:
    level: str  # "E" 或 "W"
    code: str
    where: str
    msg: str

    def render(self) -> str:
        return f"{self.level} {self.code} {self.where}: {self.msg}"


@dataclass
class Report:
    run_dir: Path
    issues: list[Issue] = field(default_factory=list)

    def err(self, code: str, where: str, msg: str) -> None:
        self.issues.append(Issue("E", code, where, msg))

    def warn(self, code: str, where: str, msg: str) -> None:
        self.issues.append(Issue("W", code, where, msg))

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "E"]


# ---------- 解析 ----------

def split_lines(text: str) -> list[str]:
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def section(lines: list[str], heading_prefix: str) -> list[str]:
    """取某个 `## ` 标题下的正文（不含该标题行，止于下一个同级标题）。"""
    out: list[str] = []
    inside = False
    for ln in lines:
        if ln.startswith("## "):
            if inside:
                break
            inside = ln.strip().startswith(heading_prefix)
            continue
        if inside:
            out.append(ln)
    return out


def table_rows(lines: list[str]) -> list[list[str]]:
    """把一段里的 markdown 表格拆成单元格；跳过表头分隔行。"""
    rows: list[list[str]] = []
    for ln in lines:
        s = ln.strip()
        if not s.startswith("|"):
            continue
        if re.fullmatch(r"\|[\s:|-]+\|", s):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        rows.append(cells)
    return rows


def strip_code(cell: str) -> str:
    return cell.replace("`", "").strip()


def parse_00(text: str) -> tuple[dict[str, dict], dict[str, int]]:
    lines = split_lines(text)
    items: dict[str, dict] = {}
    for cells in table_rows(section(lines, "## 内容清单")):
        if len(cells) < 6:
            continue
        pid = strip_code(cells[0])
        if not re.fullmatch(r"p\d{2}", pid):
            continue
        chars = strip_code(cells[4])
        items[pid] = {
            "title": cells[1],
            "media": cells[3],
            "chars": int(chars) if chars.isdigit() else None,
            "body": strip_code(cells[5]),
        }
    stats: dict[str, int] = {}
    for ln in section(lines, "## 有正文统计"):
        m = re.match(r"^-\s*(有正文|有（疑截断）|无正文)：\s*(\d+)\s*条", ln.strip())
        if m:
            key = {"有正文": "有", "有（疑截断）": "有（疑截断）", "无正文": "无"}[m.group(1)]
            stats[key] = int(m.group(2))
    return items, stats


def parse_01(text: str) -> tuple[dict[str, dict], list[str]]:
    """返回 {页ID: {title, media, source, items:[{text, cite}], advice}} 与顺序表。"""
    lines = split_lines(text)
    pages: dict[str, dict] = {}
    order: list[str] = []
    current: dict | None = None
    for ln in lines:
        m = PAGE_RE.match(ln)
        if m:
            current = {"title": m.group(2), "media": "", "source": "", "items": [], "advice": ""}
            pages[m.group(1)] = current
            order.append(m.group(1))
            continue
        if current is None:
            continue
        if ln.startswith("## "):
            current = None
            continue
        mh = re.search(r"\*\*媒体\*\*：\s*([^·]+?)\s*·\s*\*\*来源类型\*\*：\s*(\S+)", ln)
        if mh:
            current["media"] = mh.group(1).strip()
            current["source"] = mh.group(2).strip()
            continue
        ma = re.search(r"\*\*修订建议\*\*：\s*(\S+)", ln)
        if ma:
            current["advice"] = ma.group(1).strip()
            continue
        mi = NUM_ITEM_RE.match(ln)
        if mi:
            body = mi.group(1).strip()
            mc = CITE_RE.search(body)
            current["items"].append(
                {"text": body, "cite": mc.group(2) if mc else None, "cited": bool(mc)}
            )
    return pages, order


def parse_02(text: str) -> tuple[dict[str, dict], dict[str, int]]:
    pages: dict[str, dict] = {}
    current: dict | None = None
    for ln in split_lines(text):
        m = PAGE_RE.match(ln)
        if m:
            current = {"title": m.group(2), "rows": []}
            pages[m.group(1)] = current
            continue
        if ln.startswith("## "):
            if not ln.startswith("## p"):
                current = None
            continue
        if current is None or not ln.strip().startswith("|"):
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cells) < 5 or not ENTRY_ID_RE.match(cells[0]):
            continue
        current["rows"].append(
            {
                "id": cells[0],
                "point": cells[1],
                "state": cells[2],
                "source": cells[3],
                "basis": cells[4],
            }
        )
    summary: dict[str, int] = {}
    ms = re.search(
        r"汇总：共\s*(\d+)\s*条\s*·\s*直接引用\s*(\d+)\s*·\s*转述源\s*(\d+)\s*·\s*可疑\s*(\d+)", text
    )
    if ms:
        summary = {
            "total": int(ms.group(1)),
            "direct": int(ms.group(2)),
            "indirect": int(ms.group(3)),
            "suspect": int(ms.group(4)),
        }
    return pages, summary


def parse_03(text: str) -> dict:
    lines = split_lines(text)
    summary: dict[str, int] = {}
    for cells in table_rows(section(lines, "## 汇总")):
        if len(cells) >= 2 and cells[1].isdigit():
            summary[cells[0]] = int(cells[1])
    dest: dict[str, str] = {}
    for cells in table_rows(section(lines, "## 一、去向")):
        if len(cells) >= 3 and re.fullmatch(r"p\d{2}", strip_code(cells[0])):
            dest[strip_code(cells[0])] = strip_code(cells[2])
    sections: dict[str, list[list[str]]] = {
        "keep": table_rows(section(lines, "## 二、")),
        "review": table_rows(section(lines, "## 三、")),
        "fix": table_rows(section(lines, "## 四、")),
    }
    checklist = [
        ln.strip()
        for ln in section(lines, "## 待你确认的落地动作")
        if ln.strip().startswith("- [")
    ]
    return {"summary": summary, "dest": dest, "sections": sections, "checklist": checklist}


# ---------- 校验 ----------

def check_structure(rep: Report, has: dict[str, bool]) -> None:
    for name in REQUIRED_FILES:
        if not has.get(name):
            rep.err("E_MISSING_FILE", name, "缺少这份产物（四步流水线必须留下四份）")


def check_00(rep: Report, items: dict[str, dict], stats: dict[str, int]) -> None:
    if not items:
        rep.err("E_NO_ITEMS", "00-采编清单.md", "「内容清单」里没有任何 pNN 行")
    for pid, row in items.items():
        if row["body"] not in BODY_STATES:
            rep.err(
                "E_BODY_STATE",
                f"00-采编清单.md#{pid}",
                f"「有正文」只能是 {'/'.join(BODY_STATES)}，得到 {row['body']!r}",
            )
        if row["body"] == "有" and row["chars"] is not None and row["chars"] < 200:
            rep.err(
                "E_CHARS_VS_BODY",
                f"00-采编清单.md#{pid}",
                f"标了「有」但正文字符数 {row['chars']} < 200（应标「有（疑截断）」）",
            )
        if row["body"] == "无" and row["chars"] not in (None, 0) and row["chars"] >= 50:
            rep.err(
                "E_CHARS_VS_BODY",
                f"00-采编清单.md#{pid}",
                f"标了「无」但正文字符数 {row['chars']} ≥ 50",
            )
    if not stats:
        rep.err("E_NO_STATS", "00-采编清单.md", "缺「有正文统计」")
        return
    counts = {state: 0 for state in BODY_STATES}
    for row in items.values():
        if row["body"] in counts:
            counts[row["body"]] += 1
    for state, n in counts.items():
        if stats.get(state, 0) != n:
            rep.err(
                "E_STATS_MISMATCH",
                "00-采编清单.md",
                f"统计说「{state}」{stats.get(state, 0)} 条，清单里实际 {n} 条",
            )
    if sum(stats.values()) != len(items):
        rep.err(
            "E_STATS_TOTAL",
            "00-采编清单.md",
            f"统计合计 {sum(stats.values())} 条，清单 {len(items)} 行",
        )


def check_01_02(rep: Report, items_00: dict[str, dict], pages_01, order_01, pages_02, summary_02) -> None:
    if not pages_01:
        rep.err("E_NO_PAGES", "01-笔记.md", "没有任何 `## pNN · 标题` 页")
        return
    for pid in pages_01:
        if pid not in items_00:
            rep.err("E_PAGE_UNKNOWN", f"01-笔记.md#{pid}", "这一页在采编清单里没有对应条目")
        other = items_00.get(pid, {}).get("body")
        if other == "无":
            rep.warn("W_NOTE_WITHOUT_BODY", f"01-笔记.md#{pid}", "采编清单标「无正文」却写了笔记")
    for pid, page in pages_01.items():
        if not page["items"]:
            rep.warn("W_EMPTY_PAGE", f"01-笔记.md#{pid}", "这一页没有要点")
        if len(page["items"]) > 5:
            rep.err("E_TOO_MANY_POINTS", f"01-笔记.md#{pid}", f"{len(page['items'])} 条要点，上限 5 条")
        if page["source"] and page["source"] not in SOURCES:
            rep.err(
                "E_SOURCE_INVALID",
                f"01-笔记.md#{pid}",
                f"来源类型 {page['source']!r} 不在 {'/'.join(SOURCES)}",
            )
        advice = page["advice"].replace("。", "").strip()
        if advice and advice not in ADVICE:
            rep.err(
                "E_ADVICE_INVALID",
                f"01-笔记.md#{pid}",
                f"修订建议 {advice!r} 不在 {'/'.join(ADVICE)}（确认步靠它排序）",
            )
        for i, item in enumerate(page["items"], 1):
            if not item["cited"]:
                rep.err(
                    "E_NO_CITATION",
                    f"01-笔记.md#{pid}-{i}",
                    "要点结尾没有「（出处：… · 原文/OCR/ASR/Vision）」，核查官无从定位",
                )

    if not pages_02:
        rep.err("E_NO_PAGES", "02-核查表.md", "没有任何核查页")
        return
    if set(pages_02) != set(pages_01):
        missing = sorted(set(pages_01) - set(pages_02))
        extra = sorted(set(pages_02) - set(pages_01))
        rep.err(
            "E_PAGE_MISMATCH",
            "02-核查表.md",
            f"页集合与 01-笔记.md 不一致：缺 {missing or '无'}，多 {extra or '无'}",
        )

    all_rows: list[dict] = []
    for pid, page in pages_02.items():
        rows = page["rows"]
        if not rows:
            rep.warn("W_EMPTY_PAGE", f"02-核查表.md#{pid}", "这一页没有核查条目")
            continue
        expected = [f"{pid}-{n}" for n in range(1, len(rows) + 1)]
        got = [r["id"] for r in rows]
        if got != expected:
            rep.err(
                "E_ENTRY_ID_SEQ",
                f"02-核查表.md#{pid}",
                f"条目号必须从 {pid}-1 连续编号，实际 {'、'.join(got)}",
            )
        src_01 = pages_01.get(pid, {})
        for row in rows:
            all_rows.append(row)
            if row["state"] not in STATES:
                rep.err(
                    "E_STATE_INVALID",
                    f"02-核查表.md#{row['id']}",
                    f"状态 {row['state']!r} 不在三态之列",
                )
                continue
            if row["source"] not in SOURCES:
                rep.err(
                    "E_SOURCE_INVALID",
                    f"02-核查表.md#{row['id']}",
                    f"来源类型 {row['source']!r} 不在 {'/'.join(SOURCES)}",
                )
                continue
            if row["state"] == "已核实（直接引用）" and row["source"] != "原文":
                rep.err(
                    "E_STATE_SOURCE_MISMATCH",
                    f"02-核查表.md#{row['id']}",
                    f"「直接引用」却把来源记为 {row['source']}——转述源不能升格",
                )
            if row["state"] == "已核实（转述源）" and row["source"] == "原文":
                body_state = items_00.get(pid, {}).get("body")
                if body_state != "有（疑截断）":
                    rep.err(
                        "E_STATE_SOURCE_MISMATCH",
                        f"02-核查表.md#{row['id']}",
                        "「转述源」要求来源为 OCR/ASR/Vision，或该页在采编清单里是「有（疑截断）」",
                    )
            if row["state"] == "可疑" and row["source"] != "—":
                rep.err(
                    "E_STATE_SOURCE_MISMATCH",
                    f"02-核查表.md#{row['id']}",
                    f"「可疑」的来源类型应写 —，得到 {row['source']}",
                )
            if not row["basis"]:
                rep.err("E_NO_BASIS", f"02-核查表.md#{row['id']}", "「正文依据」为空")

        # 01 的引用类型应与 02 的判定一致
        if src_01.get("items"):
            for n, item in enumerate(src_01["items"], 1):
                rid = f"{pid}-{n}"
                row = next((r for r in rows if r["id"] == rid), None)
                if row is None or not item["cite"] or row["source"] in ("—", ""):
                    continue
                if item["cite"] != row["source"]:
                    rep.err(
                        "E_QUOTE_SOURCE_MISMATCH",
                        f"{rid}",
                        f"笔记标 {item['cite']}，核查表判定 {row['source']}——同一句话两个来源",
                    )

    if summary_02:
        direct = sum(1 for r in all_rows if r["state"] == "已核实（直接引用）")
        indirect = sum(1 for r in all_rows if r["state"] == "已核实（转述源）")
        suspect = sum(1 for r in all_rows if r["state"] == "可疑")
        if summary_02["total"] != len(all_rows):
            rep.err(
                "E_COUNT_TOTAL",
                "02-核查表.md",
                f"汇总写共 {summary_02['total']} 条，表里实际 {len(all_rows)} 条",
            )
        for key, actual, label in (
            ("direct", direct, "直接引用"),
            ("indirect", indirect, "转述源"),
            ("suspect", suspect, "可疑"),
        ):
            if summary_02[key] != actual:
                rep.err(
                    "E_COUNT_SPLIT",
                    "02-核查表.md",
                    f"汇总写{label} {summary_02[key]} 条，表里实际 {actual} 条",
                )
    else:
        rep.err("E_NO_SUMMARY", "02-核查表.md", "缺「> 汇总：共 N 条 · …」这一行")


def check_03(rep: Report, pages_01, pages_02, summary_02, proposal: dict) -> None:
    rows = [r for page in pages_02.values() for r in page["rows"]]
    ids = {r["id"] for r in rows}

    summary = proposal["summary"]
    if not summary:
        rep.err("E_NO_SUMMARY", "03-待确认提案.md", "「汇总」表为空")
    else:
        for state, label in (
            ("已核实（直接引用）", "direct"),
            ("已核实（转述源）", "indirect"),
            ("可疑", "suspect"),
        ):
            actual = sum(1 for r in rows if r["state"] == state)
            if summary.get(state, 0) != actual:
                rep.err(
                    "E_PROPOSAL_SUM",
                    "03-待确认提案.md",
                    f"汇总写「{state}」{summary.get(state, 0)} 条，核查表实际 {actual} 条",
                )
        if sum(summary.values()) != len(rows):
            rep.err(
                "E_PROPOSAL_SUM",
                "03-待确认提案.md",
                f"汇总合计 {sum(summary.values())} 条，核查表 {len(rows)} 条",
            )

    dest = proposal["dest"]
    if set(dest) != set(pages_01):
        rep.err(
            "E_DEST_PAGES",
            "03-待确认提案.md",
            f"「去向（按页）」应覆盖 01 的全部页：缺 {sorted(set(pages_01) - set(dest)) or '无'}，"
            f"多 {sorted(set(dest) - set(pages_01)) or '无'}",
        )

    seen: dict[str, str] = {}
    for name, label in (("keep", "二、建议保留"), ("review", "三、建议保留但需你回看"), ("fix", "四、建议修正或删除")):
        for cells in proposal["sections"][name]:
            if not cells:
                continue
            rid = strip_code(cells[0])
            if rid in ("条目", "-", ""):
                continue
            if not ENTRY_ID_RE.match(rid):
                rep.warn("W_UNKNOWN_ROW", f"03-待确认提案.md#{label}", f"第一列不是条目号：{rid!r}")
                continue
            if rid not in ids:
                rep.err("E_ORPHAN_ENTRY", f"03-待确认提案.md#{rid}", "这一条在核查表里不存在")
            if rid in seen:
                rep.err(
                    "E_DUPLICATE_ENTRY",
                    f"03-待确认提案.md#{rid}",
                    f"同一条既在「{seen[rid]}」又在「{label}」",
                )
            seen[rid] = label

    missing = ids - set(seen)
    if missing:
        rep.err(
            "E_UNCOVERED_ENTRY",
            "03-待确认提案.md",
            f"{len(missing)} 条没有归入任何一节：{sorted(missing)[:6]}{' …' if len(missing) > 6 else ''}",
        )

    for cells in proposal["sections"]["keep"]:
        if len(cells) >= 3 and strip_code(cells[0]).startswith("p"):
            basis = cells[2]
            if not any(word in basis for word in ADVICE) and "已核实" not in basis:
                rep.warn(
                    "W_WEAK_BASIS",
                    f"03-待确认提案.md#{strip_code(cells[0])}",
                    "「依据」既没引修订建议原句，也没写核查状态",
                )

    if not proposal["checklist"]:
        rep.err("E_NO_CHECKLIST", "03-待确认提案.md", "「待你确认的落地动作」为空，提案无法执行")


def validate(run_dir: Path) -> Report:
    rep = Report(run_dir)
    texts: dict[str, str] = {}
    has: dict[str, bool] = {}
    for name in REQUIRED_FILES:
        p = run_dir / name
        ok = p.is_file()
        has[name] = ok
        if ok:
            texts[name] = p.read_text(encoding="utf-8")
    check_structure(rep, has)
    if not has[REQUIRED_FILES[0]]:
        return rep

    items_00, stats = parse_00(texts.get("00-采编清单.md", ""))
    check_00(rep, items_00, stats)

    pages_01, order_01 = parse_01(texts.get("01-笔记.md", ""))
    pages_02, summary_02 = parse_02(texts.get("02-核查表.md", ""))
    check_01_02(rep, items_00, pages_01, order_01, pages_02, summary_02)

    if "03-待确认提案.md" in texts:
        check_03(rep, pages_01, pages_02, summary_02, parse_03(texts["03-待确认提案.md"]))
    return rep


def find_runs(root: Path) -> tuple[list[Path], list[Path]]:
    """返回 (当前契约的 run, 旧结构的 run)。

    2026-11 之前是五文件结构（`01-整理清单` / `02-笔记` / `03-核查表` / `04-待确认提案`），
    那些目录原样留着当存档，不该因为一次改名就让 `--all` 永远红。
    判定很简单：有没有 `01-笔记.md`。
    """
    runs = root / "runs"
    if not runs.is_dir():
        return [], []
    current: list[Path] = []
    legacy: list[Path] = []
    for d in sorted(runs.iterdir()):
        if not d.is_dir() or d.name in ("_template", "_archive"):
            continue
        (current if (d / "01-笔记.md").is_file() else legacy).append(d)
    return current, legacy


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="校验 runs/<run>/ 的四份产物是否自洽")
    ap.add_argument("run", nargs="?", help="run 目录，如 runs/2026-11-11-某主题/")
    ap.add_argument("--all", action="store_true", help="扫描仓库 runs/ 下所有 run")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args(argv)

    root = Path(__file__).resolve().parent.parent
    targets: list[Path] = []
    legacy: list[Path] = []
    if args.all:
        targets, legacy = find_runs(root)
        for d in legacy:
            print(f"-- 跳过 {d.name}（旧版五文件结构，存档不校验）")
        if not targets:
            print("没有可校验的 run（runs/ 下只有 _template / _archive、或都是旧结构）")
            return 0
    elif args.run:
        targets = [Path(args.run)]
    else:
        ap.error("要么给一个 run 目录，要么用 --all")

    bad = 0
    payload = []
    for t in targets:
        if not t.is_dir():
            print(f"E E_NOT_A_RUN {t}: 不是目录")
            return 2
        rep = validate(t)
        payload.append(
            {
                "run": str(t),
                "errors": len(rep.errors),
                "warnings": len(rep.issues) - len(rep.errors),
                "issues": [i.render() for i in rep.issues],
            }
        )
        if args.json:
            continue
        print(f"== {t}")
        if not rep.issues:
            print("   OK 四份产物自洽")
            continue
        for issue in rep.issues:
            print("  " + issue.render())
        print(f"   → {len(rep.errors)} 个错误 / {len(rep.issues) - len(rep.errors)} 个提醒")
        if rep.errors:
            bad += 1

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
