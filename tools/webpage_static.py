#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Agent 0 · 采编 — 静态网页抓取兜底（不依赖浏览器）

当 BrowserSkill（bsk）起不来、或内置浏览器打不开外网时，用 HTTP 直取 HTML，
剥掉脚本 / 样式 / 导航后取正文。它拿不到 JS 渲染出来的内容，也过不了登录墙；
那种页面照样如实报失败，不补写、不猜。

用法（一般由 extract-webpage.py 自动调用）：
    python webpage_static.py <URL> [--timeout 25]

输出 JSON（五键契约，与其余提取工具一致）：
    {"success": true, "text": "...", "char_count": 1234,
     "method": "static-http", "error": null}
"""

from __future__ import annotations

import argparse
import json
import re
import sys

try:
    import requests
except ImportError:  # pragma: no cover - 依赖缺失时由调用方给出提示
    requests = None

try:
    import lxml.html
except ImportError:  # pragma: no cover
    lxml = None

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# 这些标签整块不是正文
DROP_TAGS = {
    "script", "style", "noscript", "svg", "canvas", "video", "audio",
    "iframe", "template", "form", "button", "input", "select", "textarea",
    "nav", "footer", "header", "aside",
}

BLOCK_TAGS = {
    "p", "div", "section", "article", "main", "br", "li", "ul", "ol", "dl",
    "dt", "dd", "tr", "td", "th", "table", "h1", "h2", "h3", "h4", "h5", "h6",
    "pre", "blockquote", "figure", "figcaption", "hr", "details", "summary",
}

# 常见正文容器；按优先级取文本最多的那个
CONTENT_XPATHS = [
    '//article',
    '//*[@role="main"]',
    '//main',
    '//*[@id="js_content"]',                        # 微信公众号
    '//*[contains(@class,"rich_media_content")]',   # 微信公众号
    '//*[contains(@class,"RichText")]',             # 知乎
    '//*[contains(@class,"article-content")]',
    '//*[contains(@class,"post-content")]',
    '//*[contains(@class,"entry-content")]',
    '//*[contains(@class,"markdown-body")]',
    '//*[contains(@class,"content")]',
]

MIN_CHARS = 200


def _is_hidden(el) -> bool:
    style = (el.get("style") or "").replace(" ", "").lower()
    if "display:none" in style or "visibility:hidden" in style:
        return True
    return el.get("hidden") is not None


def _text_len(el) -> int:
    try:
        return len(re.sub(r"\s+", "", el.text_content() or ""))
    except Exception:
        return 0


def _clean_tree(root) -> None:
    for el in list(root.iter()):
        if el is root or el.getparent() is None:
            continue
        tag = el.tag if isinstance(el.tag, str) else ""
        try:
            if tag.lower() in DROP_TAGS or _is_hidden(el):
                el.drop_tree()
        except Exception:
            pass


def _pick_container(doc):
    for xpath in CONTENT_XPATHS:
        try:
            nodes = [n for n in doc.xpath(xpath) if _text_len(n) >= MIN_CHARS]
        except Exception:
            nodes = []
        if nodes:
            return max(nodes, key=_text_len)
    return doc.body if doc.body is not None else doc


def _walk(el, out: list) -> None:
    tag = el.tag if isinstance(el.tag, str) else ""
    if tag.lower() in BLOCK_TAGS:
        out.append("\n")
    if el.text:
        out.append(el.text)
    for child in el:
        _walk(child, out)
        if child.tail:
            out.append(child.tail)
    if tag.lower() in ("p", "div", "section", "li", "tr", "h1", "h2", "h3",
                       "h4", "h5", "h6", "pre", "blockquote"):
        out.append("\n")


def _normalize(raw: str) -> str:
    lines = [re.sub(r"[ \t ]+", " ", ln).strip() for ln in raw.splitlines()]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_html(html, url: str = "") -> tuple[str, str]:
    """把 HTML 转成（标题, 正文）。html 可以是 bytes 或 str。"""
    if lxml is None:
        raise RuntimeError("缺 lxml：pip install lxml")
    doc = lxml.html.fromstring(html)
    title = ""
    for xp in ('//meta[@property="og:title"]/@content', "//title/text()"):
        try:
            got = doc.xpath(xp)
        except Exception:
            got = []
        if got and str(got[0]).strip():
            title = str(got[0]).strip()
            break
    if url:
        try:
            doc.make_links_absolute(url)
        except Exception:
            pass
    _clean_tree(doc)
    container = _pick_container(doc)
    out: list = []
    _walk(container, out)
    return title, _normalize("".join(out))


def fetch_and_extract(url: str, timeout: int = 25) -> dict:
    """HTTP 直取并按五键契约返回。"""
    if not re.match(r"^https?://", url, re.I):
        return {"success": False, "text": "", "char_count": 0, "method": "error",
                "error": f"静态兜底只支持 http(s)，收到：{url[:80]}"}
    if requests is None:
        return {"success": False, "text": "", "char_count": 0, "method": "error",
                "error": "缺 requests：pip install requests"}
    if lxml is None:
        return {"success": False, "text": "", "char_count": 0, "method": "error",
                "error": "缺 lxml：pip install lxml"}

    try:
        resp = requests.get(
            url,
            timeout=timeout,
            allow_redirects=True,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
        )
    except requests.RequestException as exc:
        return {"success": False, "text": "", "char_count": 0, "method": "error",
                "error": f"HTTP 请求失败：{type(exc).__name__}: {str(exc)[:180]}"}

    ctype = (resp.headers.get("Content-Type") or "").lower()
    if resp.status_code >= 400:
        return {"success": False, "text": "", "char_count": 0, "method": "error",
                "error": f"HTTP {resp.status_code}（{ctype.split(';')[0] or '未知类型'}）"}
    if "pdf" in ctype or "json" in ctype or "image/" in ctype:
        return {"success": False, "text": "", "char_count": 0, "method": "error",
                "error": f"不是 HTML（{ctype.split(';')[0]}），换对应工具处理"}

    try:
        title, text = parse_html(resp.content, resp.url)
    except Exception as exc:
        return {"success": False, "text": "", "char_count": 0, "method": "error",
                "error": f"HTML 解析失败：{type(exc).__name__}: {str(exc)[:180]}"}

    char_count = len(text.replace("\n", ""))
    if char_count < MIN_CHARS:
        return {"success": False, "text": "", "char_count": 0, "method": "error",
                "error": (f"只取到 {char_count} 字，疑似 JS 渲染或登录墙"
                          f"（HTTP {resp.status_code}）")}

    head = f"# {title}\n\n" if title else ""
    body = head + text
    return {"success": True, "text": body,
            "char_count": len(body.replace("\n", "")),
            "method": "static-http", "error": None}


def main() -> None:
    ap = argparse.ArgumentParser(description="静态 HTTP 网页正文提取（bsk 兜底）")
    ap.add_argument("url")
    ap.add_argument("--timeout", type=int, default=25)
    args = ap.parse_args()
    print(json.dumps(fetch_and_extract(args.url, args.timeout), ensure_ascii=False))


if __name__ == "__main__":
    main()
