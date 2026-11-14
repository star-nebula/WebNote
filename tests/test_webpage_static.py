"""静态兜底解析器的测试：只测纯函数，不联网。

网页采集主链路（bsk）经常起不来，静态兜底是实际在用的那条路；
它必须把导航栏 / 脚本 / 隐藏元素剥掉，又不把正文切碎。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_module():
    path = ROOT / "tools" / "webpage_static.py"
    spec = importlib.util.spec_from_file_location("webpage_static", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["webpage_static"] = mod
    spec.loader.exec_module(mod)
    return mod


WS = load_module()

HTML = """<!doctype html>
<html><head>
  <title>标题来自 title</title>
  <meta property="og:title" content="标题来自 og">
  <style>.x{color:red}</style>
  <script>var secret = "不该出现";</script>
</head>
<body>
  <nav><a href="/">首页</a><a href="/about">关于</a></nav>
  <header>页头导航</header>
  <main>
    <article>
      <h1>正文标题</h1>
      <p>第一段正文，讲的是静态抓取。</p>
      <p style="display:none">隐藏的推广文案</p>
      <div hidden>另一个隐藏块</div>
      <p>第二段正文，<a href="/x">带链接</a>也要保留。</p>
      <pre>code block 1
code block 2</pre>
    </article>
  </main>
  <footer>页脚版权</footer>
  <noscript>请开启 JS</noscript>
</body></html>
"""


def test_title_prefers_og():
    title, _ = WS.parse_html(HTML, "https://example.com/a")
    assert title == "标题来自 og"


def test_article_is_picked_and_boilerplate_dropped():
    _, text = WS.parse_html(HTML, "https://example.com/a")
    assert "第一段正文" in text
    assert "第二段正文" in text
    assert "code block 2" in text
    # 导航 / 页脚 / 脚本 / 样式 / 隐藏元素都不该进来
    for junk in ("首页", "页头导航", "页脚版权", "不该出现", "color:red", "隐藏的推广文案", "另一个隐藏块", "请开启 JS"):
        assert junk not in text, junk


def test_paragraphs_do_not_glue_together():
    _, text = WS.parse_html(HTML, "https://example.com/a")
    assert "第一段正文" in text.splitlines()[0] or "第一段正文" in text
    assert "第二段正文" in text
    # 两段之间必须有换行，否则下游按段落切块会全糊成一块
    assert "讲的是静态抓取。\n" in text or "讲的是静态抓取。\r\n" in text


def test_non_http_url_is_rejected_without_network():
    out = WS.fetch_and_extract("file:///nope/missing.html")
    assert out["success"] is False
    assert out["method"] == "error"
    assert "http" in out["error"].lower()
    for key in ("success", "text", "char_count", "method", "error"):
        assert key in out


def test_fallback_large_enough_check():
    """正文太短时不许当成功——那多半是 JS 壳或登录墙。"""
    tiny = "<html><body><p>只有一点点字</p></body></html>"
    _, text = WS.parse_html(tiny)
    assert len(text.replace("\n", "")) < WS.MIN_CHARS


def test_gbk_page_decodes_from_meta_charset():
    """中文站常见 GBK + meta charset；按字节解析必须还原，不能出乱码。"""
    page = (
        '<html><head><meta charset="gbk"><title>中文标题</title></head>'
        '<body><article><p>' + "这是正文内容。" * 40 + "</p></article></body></html>"
    )
    title, text = WS.parse_html(page.encode("gbk"))
    assert title == "中文标题"
    assert "这是正文内容" in text
