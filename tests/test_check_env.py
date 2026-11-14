#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""子进程探活不许卡死（tools/proc.py）。

2026-11-14 的现场：`bsk browsers` 冷启动顺手拉起常驻的 `bsk daemon start`，
daemon 继承了 stdout/stderr 管道；subprocess.run(capture_output=True, timeout=8)
超时后只杀得掉 bsk.exe，communicate() 等管道关闭永远等不到，自检卡满 15 分钟
才被外层掐掉。改走临时文件后，超时 1 秒就 1 秒返回。
"""

import importlib.util
import sys
import textwrap
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


PROC = _load("proc")


def test_normal_command_returns_output():
    code, out = PROC.run_to_file([sys.executable, "-c", "print('hi')"], timeout=30)
    assert code == 0
    assert out.strip() == "hi"


def test_timeout_returns_instead_of_blocking(tmp_path):
    # 子进程再拉一个长命孙进程，并让孙进程继承 stdout/stderr：
    # 走管道时这里要等到孙进程退出（30 秒）才返回，写文件则到点就返回。
    leaker = tmp_path / "leaker.py"
    leaker.write_text(textwrap.dedent("""
        import subprocess, sys, time
        subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        time.sleep(30)
    """), encoding="utf-8")

    start = time.time()
    code, _out = PROC.run_to_file([sys.executable, str(leaker)], timeout=1)
    elapsed = time.time() - start

    assert code is None, "超时必须返回 None，不能抛异常"
    assert elapsed < 6, f"超时设 1 秒却用了 {elapsed:.1f} 秒——又卡在管道上了"


def test_check_env_reports_browser_skill_without_crashing():
    check_env = _load("check-env")
    state, _hint = check_env.check_browser_skill()
    assert state in ("可用", "需配置", "缺失")
