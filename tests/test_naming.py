"""落库命名：三档升级与文件名净化。

这是唯一会被"用到真实文件系统"的规则，写错了要么覆盖别人的笔记，
要么把文件名写成 Windows 不接受的形状。所以它被抽成纯函数单独测。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load():
    spec = importlib.util.spec_from_file_location("naming", ROOT / "tools" / "naming.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["naming"] = mod  # dataclass 解析注解时要能查到本模块
    spec.loader.exec_module(mod)
    return mod


N = load()


def test_default_is_the_title(tmp_path):
    assert N.landing_name("一篇讲缓存的文章") == "一篇讲缓存的文章.md"


def test_author_and_platform_only_on_collision():
    taken = {"一篇讲缓存的文章.md"}
    got = N.landing_name("一篇讲缓存的文章", author="张三", platform="公众号", taken=taken)
    assert got == "一篇讲缓存的文章 - 张三 - 公众号.md"


def test_date_tier_when_still_colliding():
    taken = {"标题.md", "标题 - 张三 - 公众号.md"}
    got = N.landing_name("标题", "张三", "公众号", taken=taken, today="2026-11-11")
    assert got == "标题 - 张三 - 公众号 - 2026-11-11.md"


def test_counter_when_same_day_repeats():
    taken = {
        "标题.md",
        "标题 - 张三 - 公众号.md",
        "标题 - 张三 - 公众号 - 2026-11-11.md",
    }
    got = N.landing_name("标题", "张三", "公众号", taken=taken, today="2026-11-11")
    assert got == "标题 - 张三 - 公众号 - 2026-11-11 (2).md"


def test_anonymous_author_is_marked():
    taken = {"无署名文章.md"}
    assert N.landing_name("无署名文章", platform="知乎", taken=taken) == "无署名文章 - 佚名 - 知乎.md"


def test_platform_omitted_when_unknown():
    taken = {"只有作者.md"}
    assert N.landing_name("只有作者", author="李四", taken=taken) == "只有作者 - 李四.md"


def test_collision_is_case_insensitive():
    taken = {"Mixed Case.md"}
    assert N.landing_name("mixed case", author="王五", platform="博客", taken=taken) != "mixed case.md"


@pytest.mark.parametrize("raw", ['带/斜杠', "带:冒号", "带|竖线", '带"引号', "带<尖>括号", "带?问号"])
def test_illegal_characters_are_stripped(raw):
    got = N.landing_name(raw)
    for ch in '<>:"/\\|?*':
        assert ch not in got


def test_whitespace_collapsed_and_trailing_dot_removed():
    got = N.landing_name("  多余   空格  ")
    assert got == "多余 空格.md"
    assert N.landing_name("结尾有点...") == "结尾有点.md"


def test_empty_title_falls_back():
    assert N.landing_name("   ") == "未命名.md"


def test_cli_prints_json(tmp_path, capsys):
    (tmp_path / "标题.md").write_text("x", encoding="utf-8")
    assert N.main(["标题", "--dir", str(tmp_path), "--today", "2026-11-11"]) == 0
    out = capsys.readouterr().out
    assert '"name": "标题 - 2026-11-11.md"' in out
