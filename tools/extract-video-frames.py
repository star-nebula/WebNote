#!/usr/bin/env python3
"""
Agent 0 · 采编 — 视频画面采集工具（抽帧 + OCR + Vision）

对视频抽帧，用本地 RapidOCR 提取逐字文字 + 云端 DeepSeek Vision 理解画面语义，
按时间戳对齐，输出统一 JSON 与 Markdown。

链路：
  视频 → ffmpeg 抽帧（场景变化 + 每5秒定时兜底）
       → 本地 RapidOCR 逐帧提取文字（管"准确文字"）
       → 云端 DeepSeek Vision 批量理解（每 14 帧一批，管"画面在讲什么"）
       → 时间戳对齐 → 统一 JSON + Markdown

用法：
  DEEPSEEK_API_KEY=sk-xxx python extract-video-frames.py --input <视频文件>
       [--out <输出JSON路径>] [--max-frames N] [--detail high]
       [--t-start S] [--t-end S] [--ocr-python <RapidOCR解释器>]
       [--keep-frames]        # 保留抽帧目录（默认临时目录用完即删）

依赖：
  - ffmpeg（系统已装）
  - RapidOCR（建议在独立 venv：pip install rapidocr-onnxruntime）
  - DeepSeek API Key（环境变量 DEEPSEEK_API_KEY）

输出 JSON 到 stdout（通用契约 + 扩展）：
  {"success": true, "text": "<Markdown>", "char_count": N,
   "method": "video-frames-rapid+ds-vision", "error": null,
   "per_frame": [{"file": "...", "t": 0.0, "ocr_text": "...", "vision_text": "..."}]}
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

# 本工具目录
TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
# Vision 分块：每 14 帧一个请求
VISION_BATCH = 14
# 抽帧周期（秒）与场景阈值
PERIOD = 5.0
SCENE_THRESHOLD = 0.25


def log(msg, file=sys.stderr):
    print(f"[frames] {msg}", file=file)


def summarize_ffmpeg_err(err, limit=400):
    """
    ffmpeg 的 stderr 开头是版本 banner，真正错误在末尾（如 Invalid argument）。
    取末尾并折叠空白，避免 [:200] 截到 banner 上把真实错误吞掉。
    """
    s = " ".join(err.split())
    return ("..." + s[-limit:]) if len(s) > limit else s


def run(cmd, timeout=600):
    """执行命令，返回 (returncode, stdout, stderr)。"""
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return result.returncode, result.stdout, result.stderr


def get_duration(video):
    """用 ffprobe 获取视频时长（秒）。"""
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", video,
    ]
    rc, out, _ = run(cmd)
    if rc == 0 and out.strip():
        try:
            return float(out.strip())
        except ValueError:
            return None
    return None


def extract_frames(video, out_dir, t_start=None, t_end=None, max_frames=None, period=PERIOD):
    """
    抽帧：场景变化帧 + 每 period 秒定时兜底，合并去重。
    帧名编码时间：frame_<index>_t<秒>.jpg
    返回 [(t绝对秒, 帧路径), ...] 按时间排序。
    时间戳为视频绝对时间（t_start + 帧相对偏移）。
    """
    t_start = t_start if t_start is not None else 0.0
    base_args = []
    if t_start is not None:
        base_args += ["-ss", str(t_start)]
    if t_end is not None:
        base_args += ["-to", str(t_end)]

    # 1) 周期定时帧（每 period 秒）：p_NNNN → 绝对时间 t_start + N*period
    per_dir = os.path.join(out_dir, "periodic")
    os.makedirs(per_dir, exist_ok=True)
    fps = 1.0 / period
    cmd2 = [
        "ffmpeg", "-y", *base_args, "-i", video,
        "-vf", f"fps={fps},scale=1280:-1", "-q:v", "2",
        "-start_number", "0", os.path.join(per_dir, "p_%04d.jpg"),
    ]
    log("抽周期帧...")
    rc, _, err = run(cmd2, timeout=600)
    if rc != 0:
        log(f"周期抽帧警告: {summarize_ffmpeg_err(err)}")

    frames = []
    if os.path.isdir(per_dir):
        for fn in sorted(os.listdir(per_dir)):
            if not fn.lower().endswith((".jpg", ".jpeg", ".png")):
                continue
            m = re.search(r"p_(\d+)", fn)
            if m:
                n = int(m.group(1))
                t = t_start + n * period
                frames.append((t, os.path.join(per_dir, fn)))

    # 2) 场景变化帧：用 showinfo 捕获每帧真实绝对时间
    scene_dir = os.path.join(out_dir, "scene")
    os.makedirs(scene_dir, exist_ok=True)
    scene_sel = "select='gt(scene,{})'".format(SCENE_THRESHOLD)
    # 抽帧到 stderr 打 pts 的辅助脚本方式：直接输出帧 + 用 ffprobe 逐帧反查太慢。
    # 改用 ffmpeg 直接输出带时间码：抽帧时用 -fps_mode vfr + -vf "select=...,setpts=PTS-STARTPTS"
    # 再对每张帧用 ffprobe 读 pts_time（相对 t_start），加 t_start 得绝对时间。
    cmd1 = [
        "ffmpeg", "-y", *base_args, "-i", video,
        "-vf", f"{scene_sel},setpts=PTS-STARTPTS,scale=1280:-1",
        "-vsync", "vfr", "-q:v", "2", os.path.join(scene_dir, "s_%04d.jpg"),
    ]
    log("抽场景帧...")
    rc, _, err = run(cmd1, timeout=600)
    if rc != 0:
        log(f"场景抽帧警告: {summarize_ffmpeg_err(err)}")

    if os.path.isdir(scene_dir):
        for fn in sorted(os.listdir(scene_dir)):
            if not fn.lower().endswith((".jpg", ".jpeg", ".png")):
                continue
            path = os.path.join(scene_dir, fn)
            # 用 ffprobe 读该帧 pts_time（setpts=PTS-STARTPTS 后从 0 起，即相对 t_start）
            rcp, out, _ = run([
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "frame=pts_time", "-of", "csv=p=0", path,
            ], timeout=30)
            try:
                rel = float(out.strip().splitlines()[0])
            except Exception:
                rel = None
            t = t_start + rel if rel is not None else None
            frames.append((t, path))

    # 3) 按时间去重（同整秒只留一张；t 为 None 的场景帧用兜底）
    frames_sorted = sorted(frames, key=lambda x: (x[0] is None, x[0] if x[0] is not None else 0))
    seen = {}
    for t, path in frames_sorted:
        key = round(t) if t is not None else round(len(seen) * period + t_start)
        if key not in seen:
            seen[key] = (t, path)
    frames = sorted(seen.values(), key=lambda x: x[0])

    # 4) 降采样到 max_frames
    if max_frames and len(frames) > max_frames:
        idx = [round(i * (len(frames) - 1) / (max_frames - 1)) for i in range(max_frames)]
        frames = [frames[i] for i in dict.fromkeys(idx)]

    return frames


def ocr_all(frame_paths, ocr_python):
    """
    用独立 RapidOCR venv 批量 OCR。一个 subprocess 处理所有帧，避免每帧重建模型。
    返回 {t: ocr_text}
    """
    if not frame_paths:
        return {}
    # 生成一个临时 Python 脚本：一次初始化引擎，循环处理所有帧
    script = r'''
import sys, json
from rapidocr_onnxruntime import RapidOCR
engine = RapidOCR()
paths = sys.argv[1:]
result = {}
for p in paths:
    try:
        r, _ = engine(p)
        result[p] = "\n".join(it[1] for it in r) if r else ""
    except Exception as e:
        result[p] = "[OCR error] " + str(e)
print(json.dumps(result, ensure_ascii=False))
'''
    cmd = [ocr_python, "-c", script] + [p for _, p in frame_paths]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        # 取最后一行 JSON
        data = json.loads(proc.stdout.strip().splitlines()[-1])
        out = {}
        for t, p in frame_paths:
            out[t] = data.get(p, "")
        return out
    except Exception as e:
        log(f"OCR 失败: {e}")
        return {t: "[OCR 失败]" for t, _ in frame_paths}


def vision_all(frame_paths, ocr_python=None):
    """
    用 ds_vision.py 批量理解，每 VISION_BATCH 帧一批。
    返回 {t: vision_text}
    """
    out = {}
    for i in range(0, len(frame_paths), VISION_BATCH):
        batch = frame_paths[i:i + VISION_BATCH]
        paths = [p for _, p in batch]
        times = [f"{t:.0f}s" for t, _ in batch]
        cmd = [
            sys.executable, os.path.join(TOOLS_DIR, "ds_vision.py"),
        ] + paths + ["--times", ",".join(times), "--mode", "frames"]
        log(f"Vision 批次 {i // VISION_BATCH + 1}（{len(batch)} 帧）...")
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            data = json.loads(proc.stdout.strip().splitlines()[-1])
            if data.get("success"):
                per = data.get("per_image", [])
                for j, (t, _) in enumerate(batch):
                    out[t] = per[j].get("text", "") if j < len(per) else ""
            else:
                for t, _ in batch:
                    out[t] = f"[Vision 失败] {data.get('error', '')}"
        except Exception as e:
            for t, _ in batch:
                out[t] = f"[Vision 失败] {e}"
    return out


def build_markdown(frames, ocr_map, vision_map, t_start, t_end, method):
    lines = []
    lines.append("# 视频画面理解")
    lines.append("")
    lines.append(f"> 时间段：{t_start:.0f}s - {t_end:.0f}s · 共 {len(frames)} 帧")
    lines.append(f"> 语义来源：DeepSeek-V4-Flash-Vision-Exp（云端） · 文字来源：RapidOCR（本地）")
    lines.append("")
    lines.append("## 画面语义（Vision）")
    lines.append("")
    for t, _ in frames:
        v = vision_map.get(t, "")
        if v:
            lines.append(v)
            lines.append("")
    lines.append("## 画面文字（OCR）")
    lines.append("")
    for t, _ in frames:
        o = ocr_map.get(t, "")
        lines.append(f"### t={t:.0f}s")
        lines.append("")
        lines.append(o if o.strip() else "_(未识别到文字)_")
        lines.append("")
    lines.append("## 时间戳对齐说明")
    lines.append("")
    lines.append("- **Vision** 提供“这个时间点画面在讲什么”（语义）")
    lines.append("- **OCR** 提供“这个时间点画面上的逐字文字”（精确提取）")
    lines.append("- 两者按 t 对齐，交叉校验")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="本地视频文件路径")
    ap.add_argument("--out", default=None, help="输出 JSON 文件路径（默认仅 stdout）")
    ap.add_argument("--max-frames", type=int, default=None, help="最多处理帧数（降采样）")
    ap.add_argument("--detail", default="high", choices=["low", "high", "original"])
    ap.add_argument("--t-start", type=float, default=None)
    ap.add_argument("--t-end", type=float, default=None)
    ap.add_argument("--ocr-python", default=None, help="RapidOCR 解释器路径")
    ap.add_argument("--keep-frames", action="store_true", help="保留抽帧目录")
    args = ap.parse_args()

    if not os.path.isfile(args.input):
        fail = {"success": False, "text": "", "char_count": 0, "method": "error",
                "error": f"视频文件不存在: {args.input}"}
        print(json.dumps(fail, ensure_ascii=False)); sys.exit(1)

    # 确定 RapidOCR 解释器（优先级：--ocr-python > OCR_PYTHON > 当前解释器自带 > 本机遗留 venv）
    ocr_python = args.ocr_python or os.environ.get("OCR_PYTHON", "")
    if not ocr_python:
        try:
            subprocess.run(
                [sys.executable, "-c", "import rapidocr_onnxruntime"],
                capture_output=True, timeout=30, check=True,
            )
            ocr_python = sys.executable  # 当前解释器已装 RapidOCR，直接用（通用路径）
        except Exception:
            pass
    if not ocr_python:
        # 环境变量兜底（换机器请用 --ocr-python / OCR_PYTHON 指定）
        for cand in [os.environ.get("OCR_PYTHON", "")]:
            if os.path.isfile(cand):
                ocr_python = cand
                break
    if not ocr_python:
        fail = {"success": False, "text": "", "char_count": 0, "method": "error",
                "error": "未找到 RapidOCR 解释器，请用 --ocr-python 指定"}
        print(json.dumps(fail, ensure_ascii=False)); sys.exit(1)

    # 校验 Key
    if not os.environ.get("DEEPSEEK_API_KEY"):
        fail = {"success": False, "text": "", "char_count": 0, "method": "error",
                "error": "未设置 DEEPSEEK_API_KEY 环境变量"}
        print(json.dumps(fail, ensure_ascii=False)); sys.exit(1)

    # 时长
    dur = get_duration(args.input)
    t_start = args.t_start if args.t_start is not None else 0.0
    t_end = args.t_end if args.t_end is not None else (dur or t_start + 1)

    # 临时工作目录
    tmpdir = tempfile.mkdtemp(prefix="vframes_")
    try:
        frames = extract_frames(args.input, tmpdir, t_start, t_end, args.max_frames)
        log(f"共抽到 {len(frames)} 帧")
        if not frames:
            fail = {"success": False, "text": "", "char_count": 0, "method": "error",
                    "error": "未抽到任何帧"}
            print(json.dumps(fail, ensure_ascii=False)); sys.exit(1)

        ocr_map = ocr_all(frames, ocr_python)
        vision_map = vision_all(frames)

        md = build_markdown(frames, ocr_map, vision_map, t_start, t_end, "video-frames")
        per_frame = [{
            "file": os.path.basename(p), "t": t,
            "ocr_text": ocr_map.get(t, ""), "vision_text": vision_map.get(t, ""),
        } for t, p in frames]

        out = {
            "success": True,
            "text": md,
            "char_count": len(md.replace("\n", "").replace(" ", "")),
            "method": "video-frames-rapid+ds-vision",
            "error": None,
            "frame_count": len(frames),
            "per_frame": per_frame,
        }
        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False, indent=2)
            log(f"已写入 {args.out}")
        print(json.dumps(out, ensure_ascii=False))
    finally:
        if not args.keep_frames:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
