#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WebNote 环境自检

检查当前环境能用哪些功能、缺哪些依赖，并给出补齐提示。
只用标准库，clone 下来即可运行，无需先装任何东西。

用法：
    python tools/check-env.py
    python tools/check-env.py --json     # 输出 JSON，供自动化使用
"""

import argparse
import importlib.util
import json
import os
import shutil
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from proc import run_to_file  # noqa: E402  同目录工具：命令输出写文件，避免管道卡死

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# (能力名, 依赖类型, 依赖值, 缺失时的补齐提示)
CAPABILITIES = [
    ("PDF / DOCX 文档提取", "module", ["pypdf", "docx"],
     "pip install pypdf python-docx"),
    ("网页正文提取（静态兜底）", "module", ["requests", "lxml"],
     "pip install requests lxml"),
    ("网页正文提取（BrowserSkill 浏览器）", "browser_skill", None,
     "可选。daemon 无浏览器时 extract-webpage.py 自动改走静态抓取"),
    ("图片 OCR 逐字文字", "module", ["rapidocr_onnxruntime"],
     "pip install rapidocr-onnxruntime"),
    ("图片 / 视频画面语义", "env", "DEEPSEEK_API_KEY",
     'export DEEPSEEK_API_KEY="sk-xxx"（仅画面理解需要）'),
    ("视频语音 ASR 转写", "module", ["faster_whisper"],
     "pip install faster-whisper"),
    ("视频下载 / 抽帧", "cli", "ffmpeg",
     "Windows: winget install Gyan.FFmpeg | macOS: brew install ffmpeg"),
    ("防复制页 / 云文档无损拓存", "web_archive", None,
     "需要 PowerShell 与 Chrome 或 Edge；仅 Windows 脚本链已实现"),
]


def check_module(names):
    missing = [n for n in names if importlib.util.find_spec(n) is None]
    return missing


def check_web_archive():
    shell = shutil.which("pwsh") or shutil.which("powershell")
    browsers = []
    for path in (
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ):
        if os.path.isfile(path):
            browsers.append(path)
    return bool(shell and browsers), bool(shell), bool(browsers)


def check_browser_skill():
    """bsk 装没装、daemon 有没有真的连上浏览器。

    只看可执行文件在不在会误报「可用」——2026-11-13 实测 bsk 在 PATH 上，
    但 `bsk browsers` 返回空，采集必然失败。
    """
    if shutil.which("bsk") is None:
        return "缺失", "装 BrowserSkill 后确认 `bsk --version` 能跑"
    try:
        code, stdout = run_to_file(["bsk", "browsers", "--json"], timeout=8)
    except OSError:
        return "需配置", "bsk 无法执行；直接走静态兜底即可"
    if code is None:
        return "需配置", "bsk daemon 无响应；直接走静态兜底即可"
    try:
        browsers = json.loads(stdout.strip() or "[]")
    except json.JSONDecodeError:
        browsers = None
    if isinstance(browsers, list) and browsers:
        return "可用", ""
    return "需配置", "daemon 没连上浏览器（需要在有 browser-skill 扩展的浏览器里连）"


def probe():
    """返回 [(能力名, 状态, 提示)]，状态 ∈ 可用 / 需配置 / 缺失"""
    results = []
    for name, kind, value, hint in CAPABILITIES:
        if kind == "module":
            missing = check_module(value)
            state = "可用" if not missing else "缺失"
            if missing:
                hint = f"{hint}（缺 {'、'.join(missing)}）"
        elif kind == "cli":
            state = "可用" if shutil.which(value) else "缺失"
        elif kind == "env":
            state = "可用" if os.environ.get(value) else "需配置"
        elif kind == "browser_skill":
            state, hint = check_browser_skill()
        elif kind == "web_archive":
            ready, has_shell, has_browser = check_web_archive()
            state = "可用" if ready else "缺失"
            if not ready:
                missing = []
                if not has_shell:
                    missing.append("PowerShell")
                if not has_browser:
                    missing.append("Chrome/Edge")
                hint = f"{hint}（缺 {'、'.join(missing)}）"
        else:
            state = "缺失"
        results.append((name, state, hint))
    return results


def render_text(results):
    line = "=" * 62
    print(line)
    print("WebNote 环境自检")
    print(line)

    print("\n[核心流程] 始终可用，不依赖任何东西\n")
    print("  四步工作流 + 两个角色定义 + 三态核查        可用")
    print("  图文内容整理（正文由你自己提供）            可用")
    print("\n  也就是说：你什么都不装，这套流程也能跑。")
    print("  下面的依赖只决定你能处理哪些额外的媒体类型。\n")

    print(line)
    print("[采编能力]\n")
    width = max(len(n) for n, _, _ in results)
    for name, state, _ in results:
        print(f"  {name.ljust(width)}    {state}")

    print("\n" + line)
    print("[需要补齐的]\n")
    pending = [(n, h) for n, s, h in results if s != "可用"]
    if not pending:
        print("  无。全部能力均已就绪。")
    else:
        for name, hint in pending:
            print(f"  · {name}")
            print(f"      {hint}")

    print("\n" + line)
    print("提示：能力缺失不会让流程失败，只影响对应媒体的处理。")
    print("      没有 ffmpeg 就处理不了视频，图文流程照常可用。")
    print(line)


def main():
    parser = argparse.ArgumentParser(description="WebNote 环境自检")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    results = probe()
    if args.json:
        print(json.dumps(
            [{"capability": n, "state": s, "hint": h} for n, s, h in results],
            ensure_ascii=False, indent=2))
    else:
        render_text(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
