#!/usr/bin/env python3
"""
Agent 0 · 采编 — 网页文本提取工具（通过 BrowserSkill）

通过 bsk CLI 操控浏览器读取图文页面的可见文本，输出 JSON 到 stdout。

用法：
  python extract-webpage.py <URL>

依赖：bsk CLI（已安装）
"""

import json
import shutil
import subprocess
import sys


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


def run_bsk(args, timeout=30):
    """运行 bsk 命令，返回 stdout"""
    try:
        result = subprocess.run(
            ['bsk'] + args,
            capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return '', -1
    except FileNotFoundError:
        return '', -2


def main():
    if len(sys.argv) < 2:
        output = {
            'success': False, 'text': '', 'char_count': 0,
            'method': 'error', 'error': '用法: python extract-webpage.py <URL>'
        }
        print(json.dumps(output, ensure_ascii=False))
        sys.exit(1)

    url = sys.argv[1]

    if shutil.which('bsk') is None:
        print(json.dumps({
            'success': False, 'text': '', 'char_count': 0, 'method': 'error',
            'error': (
                '找不到 bsk：BrowserSkill 未安装或未加入 PATH。\n'
                '装好后确认 `bsk --version` 能跑；命令速查用 `bsk --help`；'
                '说明副本见 skills/browser-skill/SKILL.md。'
            ),
        }, ensure_ascii=False))
        sys.exit(2)

    # 1. 创建会话
    stdout, rc = run_bsk(['session', 'start'])
    if rc != 0:
        output = {
            'success': False, 'text': '', 'char_count': 0,
            'method': 'error',
            'error': f'bsk session start 失败: bsk 未安装或 daemon 未运行'
        }
        print(json.dumps(output, ensure_ascii=False))
        sys.exit(1)

    session_id = stdout.strip()
    if not session_id:
        output = {
            'success': False, 'text': '', 'char_count': 0,
            'method': 'error', 'error': 'bsk 未返回 session ID'
        }
        print(json.dumps(output, ensure_ascii=False))
        sys.exit(1)

    try:
        # 2. 导航
        stdout, rc = run_bsk(['navigate', '--session', session_id, url])
        if rc != 0:
            output = {
                'success': False, 'text': '', 'char_count': 0,
                'method': 'error',
                'error': f'导航失败: {stdout[:200] if stdout else "浏览器扩展未连接"}'
            }
            print(json.dumps(output, ensure_ascii=False))
            return

        # 3. 等待页面加载
        run_bsk(['wait-ms', '3000'])

        # 4. evaluate JS
        stdout, rc = run_bsk(
            ['evaluate', '--session', session_id, '--json', EXTRACT_VISIBLE_TEXT_JS],
            timeout=30
        )

        if rc != 0 or not stdout:
            output = {
                'success': False, 'text': '', 'char_count': 0,
                'method': 'error',
                'error': f'JS evaluate 失败 ({rc}): {stdout[:200] if stdout else "浏览器扩展可能未连接"}'
            }
            print(json.dumps(output, ensure_ascii=False))
            return

        # 5. 解析 JSON（bsk --json 可能包裹输出）
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            output = {
                'success': True, 'text': stdout, 'char_count': len(stdout.replace('\n', '')),
                'method': 'bsk-webpage-raw', 'error': None
            }
            print(json.dumps(output, ensure_ascii=False))
            return

        # bsk --json 输出格式: {"ok": true, "tab_id": ..., "value": "..."}
        # value 可能是 JSON 字符串（需要二次解析），也可能是普通字符串
        raw = None
        if isinstance(data, dict) and 'value' in data:
            raw = data['value']
        elif isinstance(data, dict) and 'data' in data:
            raw = data['data']
        else:
            raw = stdout

        # 尝试二次解析（value 是 JSON 字符串的情况）
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    data = parsed
                else:
                    data = raw
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
            output = {
                'success': True, 'text': text, 'char_count': char_count,
                'method': 'bsk-webpage', 'error': None
            }
        else:
            output = {
                'success': False, 'text': '', 'char_count': 0,
                'method': 'error', 'error': '页面未提取到可见文本'
            }

        print(json.dumps(output, ensure_ascii=False))

    finally:
        run_bsk(['session', 'stop', '--session', session_id], timeout=10)


if __name__ == '__main__':
    main()
