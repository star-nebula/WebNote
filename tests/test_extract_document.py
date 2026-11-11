"""真 PDF 的成功路径：不联网、不需要 API key。

之前的提取契约只测失败分支（因为成功分支要 bsk / 模型 / ffmpeg）。
PDF 是例外：pypdf 在依赖里，文件自己造一份就能跑通，所以成功路径应该被盖住。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "extract-document.py"

pytest.importorskip("pypdf", reason="pypdf 缺了就测不了 PDF 提取")


def minimal_pdf(text: str = "Hello PDF 123") -> bytes:
    """手写一份最小合法 PDF（单页、Helvetica、一行文字）。"""
    content = f"BT /F1 18 Tf 20 100 Td ({text}) Tj ET".encode()
    objs = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 200]"
        b"/Resources<</Font<</F1 4 0 R>>>>/Contents 5 0 R>>",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
        b"<</Length %d>>stream\n" % len(content) + content + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj" % i + obj + b"endobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n" % (len(objs) + 1) + b"0000000000 65535 f \n"
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<</Size %d/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return bytes(out)


def run_tool(*args: str, expect_zero: bool = True) -> dict:
    r = subprocess.run(
        [sys.executable, str(TOOL), *args],
        cwd=ROOT,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    if expect_zero:
        assert r.returncode == 0, f"退出码 {r.returncode}\n{(r.stdout or '')[-500:]}\n{(r.stderr or '')[-500:]}"
    return json.loads((r.stdout or "").strip().splitlines()[-1])


def test_pdf_success_path(tmp_path):
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(minimal_pdf())

    out = run_tool(str(pdf))

    assert out["success"] is True, out
    assert out["method"] == "pypdf"
    assert "Hello PDF 123" in out["text"]
    assert out["char_count"] == len(out["text"].replace("\n", ""))
    assert out["error"] is None


def test_missing_pdf_still_reports_contract(tmp_path):
    """失败分支也要守住同一份契约（成功分支通过之后，失败分支容易被人改坏）。"""
    out = run_tool(str(tmp_path / "nope.pdf"), expect_zero=False)
    assert out["success"] is False
    assert out["method"] == "error"
    assert out["char_count"] == 0
    assert isinstance(out["error"], str) and out["error"]
