"""跨盘路径：同盘给相对路径，异盘不能崩。

`os.path.relpath` 在 Windows 跨盘符时抛 `ValueError`，2026-11 真崩过一次
（图片在 D 盘、工作目录在 E 盘），当时的报错信息正文里甚至写着"路径正常"。
"""

from __future__ import annotations

import importlib.util
import sys
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load():
    spec = importlib.util.spec_from_file_location("safe_path", ROOT / "tools" / "safe_path.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["safe_path"] = mod  # dataclass 解析注解时要能查到本模块
    spec.loader.exec_module(mod)
    return mod


S = load()


def test_same_drive_gives_relative_path():
    base = str(ROOT)
    got = S.safe_relpath(str(ROOT / "tools" / "naming.py"), base)
    assert got == "tools/naming.py"


def test_backslashes_are_normalised():
    got = S.safe_relpath("E:\\a\\b.txt", "E:\\a")
    assert "\\" not in got


def test_cross_drive_degrades_to_basename(monkeypatch):
    def boom(path, base):
        raise ValueError("path is on mount 'D:', start on mount 'E:'")

    monkeypatch.setattr(os.path, "relpath", boom)
    assert S.safe_relpath("D:/imgs/one.png", "E:/Projects/bots/WebNote") == "one.png"


def test_production_tool_uses_the_shared_helper():
    """不许再有第二份 try/except relpath——那就等于把崩溃点复制了一遍。"""
    src = (ROOT / "tools" / "extract-image-ocr.py").read_text(encoding="utf-8")
    assert "from safe_path import safe_relpath" in src
    assert "def safe_relpath" not in src
