#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跑外部命令并收集输出：结果写临时文件，不走管道。

为什么不用 subprocess.run(capture_output=True, timeout=...)：有些命令会顺手拉起
常驻的后台进程，而后台进程继承了 stdout/stderr 的管道句柄。超时那一刻只杀得掉
直接子进程，Python 等管道关闭却要等到后台进程退出——命令有 timeout 也照样卡死。

2026-11-14 实测：`bsk browsers` 冷启动时会拉起 `bsk daemon start`，
check-env 的 8 秒超时形同虚设，自检卡满 15 分钟才被外层掐掉。
换成临时文件后，超时 1 秒就 1 秒返回，后台进程留着不管即可。
"""

import subprocess
import tempfile


def run_to_file(cmd, timeout, text=True):
    """跑命令，返回 (退出码, stdout)；超时返回 (None, 已有输出)。

    只杀直接子进程；它拉起的常驻后台进程故意留着。
    """
    with tempfile.TemporaryFile(mode="w+b") as out, \
            tempfile.TemporaryFile(mode="w+b") as err:
        proc = subprocess.Popen(cmd, stdout=out, stderr=err,
                                stdin=subprocess.DEVNULL)
        timed_out = False
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                proc.kill()
                proc.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                pass
        out.seek(0)
        raw = out.read()
    stdout = raw.decode("utf-8", "replace") if text else raw
    return (None if timed_out else proc.returncode), stdout
