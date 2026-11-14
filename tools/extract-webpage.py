#!/usr/bin/env python3
"""
Agent 0 · 采编 — 网页文本提取（bsk 优先，静态 HTTP 兜底）

先用 BrowserSkill（bsk）读浏览器里的可见文本；bsk 不可用、daemon 没连上
浏览器、或取回空正文时，自动改用 HTTP 直取 HTML 剥正文（webpage_static.py）。
两条路都不行就如实报错，不补写、不猜。

用法：
  python extract-webpage.py <URL> [--engine auto|browser|static] [--timeout 25]

依赖：bsk CLI（可选）、requests + lxml（静态兜底）
"""

import argparse
import json
import os
import shutil
import sys

# 同目录模块：直接执行、被 runpy 载入、被别的工具调用时都能找到
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from proc import run_to_file
from webpage_static import fetch_and_extract


# 单行压缩的 JS（提取页面可见文本）
EXTRACT_VISIBLE_TEXT_JS = (
    '(function(){'
    'var e=["script","style","noscript","svg","canvas","video","audio"];'
    'var t=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT,{acceptNode:function(n){'
    'var r=n.parentElement;if(!r)return NodeFilter.FILTER_REJECT;'
    'var i=r.tagName?r.tagName.toLowerCase():"";'
    'if(e.indexOf(i)!==-1)return NodeFilter.FILTER_REJECT;'
    'var s=window.getComputedStyle(r);'
    'if(s.display==="none"||s.visibility==="hidden")return NodeFilter.FILTER_REJECT;'
    'if(r.offsetWidth===0&&r.offsetHeight===0)return NodeFilter.FILTER_REJECT;'
    'return NodeFilter.FILTER_ACCEPT}},false);'
    'var a=[],n;while(n=t.nextNode()){var o=n.textContent.trim();if(o.length>0)a.push(o)}'
    'return JSON.stringify({title:document.title,text:a.join("\\n"),charCount:a.join("").length})'
    '})()'
)


def run_bsk(args, timeout=15):
    """运行 bsk 命令，返回 (stdout, 退出码)。

    走 run_to_file 而不是 capture_output=True：bsk 会顺手拉起常驻的
    `bsk daemon start`，daemon 继承了管道句柄，超时只杀得掉 bsk.exe、
    等管道关闭却永远等不到——timeout 形同虚设（2026-11-14 实测 8 秒卡成 3 分钟以上）。
    写临时文件后，超时到点就返回，退出码记 -1。
    """
    try:
        code, stdout = run_to_file(['bsk'] + args, timeout=timeout)
    except OSError:
        return '', -2
    if code is None:
        return '', -1
    return stdout.strip(), code


def fail(message):
    return {
        'success': False, 'text': '', 'char_count': 0,
        'method': 'error', 'error': message,
    }


def bsk_extract(url):
    """走 BrowserSkill 取可见文本。返回五键 dict。"""
    if shutil.which('bsk') is None:
        return fail('找不到 bsk：BrowserSkill 未安装或未加入 PATH')

    # 1. 创建会话
    stdout, rc = run_bsk(['session', 'start'], timeout=10)
    if rc != 0 or not stdout.strip():
        detail = stdout[:160] if stdout else '浏览器扩展未连接'
        return fail(f'bsk session start 失败: {detail}')

    session_id = stdout.strip()
    try:
        # 2. 导航
        stdout, rc = run_bsk(['navigate', '--session', session_id, url])
        if rc != 0:
            detail = stdout[:200] if stdout else '浏览器扩展未连接'
            return fail(f'导航失败: {detail}')

        # 3. 等待页面加载
        run_bsk(['wait-ms', '3000'])

        # 4. evaluate JS
        stdout, rc = run_bsk(
            ['evaluate', '--session', session_id, '--json', EXTRACT_VISIBLE_TEXT_JS],
            timeout=30
        )
        if rc != 0 or not stdout:
            detail = stdout[:200] if stdout else '浏览器扩展可能未连接'
            return fail(f'JS evaluate 失败 ({rc}): {detail}')

        # 5. 解析 JSON（bsk --json 可能包裹输出）
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            text = stdout
            return {
                'success': True, 'text': text,
                'char_count': len(text.replace('\n', '')),
                'method': 'bsk-webpage-raw', 'error': None,
            }

        # bsk --json 输出格式: {"ok": true, "tab_id": ..., "value": "..."}
        raw = None
        if isinstance(data, dict) and 'value' in data:
            raw = data['value']
        elif isinstance(data, dict) and 'data' in data:
            raw = data['data']
        else:
            raw = stdout

        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                data = parsed if isinstance(parsed, dict) else raw
            except (json.JSONDecodeError, TypeError):
                data = raw
        else:
            data = raw

        text = ''
        char_count = 0
        if isinstance(data, dict):
            text = data.get('text', '')
            char_count = data.get('charCount', 0)
            if not char_count and text:
                char_count = len(text.replace('\n', ''))

        if char_count > 0:
            return {
                'success': True, 'text': text, 'char_count': char_count,
                'method': 'bsk-webpage', 'error': None,
            }
        return fail('页面未提取到可见文本')
    finally:
        run_bsk(['session', 'stop', '--session', session_id], timeout=10)


def main():
    ap = argparse.ArgumentParser(description='网页正文提取（bsk 优先，静态 HTTP 兜底）')
    ap.add_argument('url')
    ap.add_argument('--engine', default='auto', choices=['auto', 'browser', 'static'],
                    help='auto=先 bsk 后静态（默认）；browser=只走 bsk；static=只走 HTTP')
    ap.add_argument('--timeout', type=int, default=25, help='静态兜底的 HTTP 超时秒数')
    args = ap.parse_args()

    if args.engine == 'static':
        print(json.dumps(fetch_and_extract(args.url, args.timeout), ensure_ascii=False))
        return

    browser = bsk_extract(args.url)
    if browser['success'] or args.engine == 'browser':
        print(json.dumps(browser, ensure_ascii=False))
        return

    static = fetch_and_extract(args.url, args.timeout)
    if static['success']:
        print(json.dumps(static, ensure_ascii=False))
        return

    print(json.dumps(fail(
        f"浏览器采集失败（{browser['error']}）；静态兜底也失败（{static['error']}）"
    ), ensure_ascii=False))


if __name__ == '__main__':
    main()
