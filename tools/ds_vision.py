#!/usr/bin/env python3
"""
Agent 0 · 采编 — 多图理解工具（画面语义）

对一组图片（如视频抽帧）理解每帧的画面语义。OCR 管"逐字文字提取"，
本工具管"画面在讲什么 / 是什么场景"。

两条通道，按顺序自动选：
  1. 本机 magpie 网关（默认）：http://127.0.0.1:3425/v1
     模型 open-design/deepseek-v4-flash-vision-exp（与官方 API 同一模型，走订阅，不用另配 Key）
  2. DeepSeek 官方 API：DEEPSEEK_API_KEY 存在时可用，模型 deepseek-v4-flash-vision-exp

用法：
  python ds_vision.py <img1.jpg> [img2.jpg ...] [--detail high]
       [--times "0s,5s,10s"] [--prompt "<自定义提示词>"] [--mode image|frames]
       [--provider auto|magpie|deepseek]

环境变量：
  MAGPIE_BASE_URL        覆盖网关地址（默认 http://127.0.0.1:3425/v1）
  MAGPIE_VISION_MODEL    覆盖网关上的视觉模型（默认 open-design/deepseek-v4-flash-vision-exp）
  DEEPSEEK_API_KEY       官方通道的 Key，绝不写进代码 / 提交 git

关键细节（必须保留）：
  * reasoning_effort:"none" —— 否则模型思考占满 max_tokens，正文返回空。
  * detail:"high"（默认）—— 保持原图；"low" 压到 512x512 会诱发幻觉。
  * 单图最多 384 token，单请求最多 600 图；建议调用方按 14 帧/批切分后多次调用。

输出 JSON 到 stdout（通用契约 + 扩展）：
  {"success": true, "text": "<逐帧语义 Markdown>", "char_count": N,
   "method": "ds-vision-<provider>-<model>-<mode>", "error": null,
   "per_image": [{"file": "...", "t": "125s", "text": "..."}]}
"""
import argparse
import base64
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.request

MAGPIE_BASE_URL = os.environ.get("MAGPIE_BASE_URL", "http://127.0.0.1:3425/v1").rstrip("/")
MAGPIE_MODEL = os.environ.get("MAGPIE_VISION_MODEL", "open-design/deepseek-v4-flash-vision-exp")
MAGPIE_TOKEN = os.environ.get("MAGPIE_TOKEN", "magpie")

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-v4-flash-vision-exp"


def log(msg, file=sys.stderr):
    print(f"[vision] {msg}", file=file)


def b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def data_url(path):
    mime = mimetypes.guess_type(path)[0] or "image/jpeg"
    return f"data:{mime};base64,{b64(path)}"


def build_instruction(times=None, user_prompt=None, mode="image"):
    """构造提示词。
    mode="image"：普通图片（描述内容/场景/文字）
    mode="frames"：视频抽帧（带时间戳，逐帧语义）
    """
    if user_prompt:
        return user_prompt
    if mode == "frames":
        times_hint = ""
        if times:
            times_hint = f"每张对应的真实时间戳依次是：{', '.join(times)}。"
        return (
            f"下面按顺序给你若干张视频截图。{times_hint}\n"
            "请逐张用中文回答，每张以【图N @ 真实时间戳】开头（时间戳用上面给的，不要自编）。\n"
            "1) 这是什么界面/场景？\n2) 在做什么操作/处于什么阶段？\n"
            "3) 抄录能看清的主要文字（看不清用[?]标注，不要编造）。\n"
            "每张控制在100字内，简洁。"
        )
    # 默认：普通图片语义理解
    return (
        "下面给你一张或多张图片。请逐张用中文回答，每张以【图N】开头：\n"
        "1) 这是什么内容？什么场景/物体/界面？\n"
        "2) 画面里主要有哪些文字（标题、按钮、提示词等），逐字抄录可看清的，看不清用[?]标注，不要编造。\n"
        "每张控制在100字内，简洁。"
    )


def _post(url, headers, payload, timeout=180):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers=headers,
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def ask_magpie(image_paths, detail="high", times=None, user_prompt=None, mode="image"):
    instruction = build_instruction(times, user_prompt, mode)
    content = [{"type": "text", "text": instruction}]
    for p in image_paths:
        content.append({
            "type": "image_url",
            "image_url": {"url": data_url(p), "detail": detail},
        })
    payload = {
        "model": MAGPIE_MODEL,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 3000,
        "stream": False,
        "reasoning_effort": "none",
    }
    return _post(
        f"{MAGPIE_BASE_URL}/chat/completions",
        {"Content-Type": "application/json", "Authorization": f"Bearer {MAGPIE_TOKEN}"},
        payload,
    )


def ask_deepseek(api_key, image_paths, detail="high", times=None, user_prompt=None, mode="image"):
    instruction = build_instruction(times, user_prompt, mode)
    content = [{"type": "text", "text": instruction}]
    for p in image_paths:
        content.append({
            "type": "image_url",
            "image_url": {"url": data_url(p), "detail": detail},
        })
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 3000,
        "stream": False,
        "reasoning_effort": "none",
    }
    return _post(
        DEEPSEEK_URL,
        {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        payload,
    )


def parse_vision_to_per_image(vision_text, image_paths, times):
    """把 Vision 的逐段输出拆成 per_image（尽力而为；若解析失败则整段放第一项）。"""
    import re
    # 按【图N 开头切分；blocks[0] 通常是空（split 在开头切）
    blocks = [b for b in re.split(r'(?=【图\d)', vision_text or "") if b.strip()]
    per = []
    for i, (path, t) in enumerate(zip(image_paths, times or [""] * len(image_paths))):
        block = blocks[i] if i < len(blocks) else ""
        per.append({"file": path, "t": t, "text": block.strip()})
    return per


def providers(requested):
    """按优先级给出可尝试的通道。"""
    out = []
    if requested in ("auto", "magpie"):
        out.append(("magpie", MAGPIE_MODEL, None))
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if requested in ("auto", "deepseek") and key:
        out.append(("deepseek", DEEPSEEK_MODEL, key))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="+", help="图片路径")
    ap.add_argument("--detail", default="high", choices=["low", "high", "original"])
    ap.add_argument("--times", default=None, help="逗号分隔的时间戳，如 '125s,145s,160s'（视频帧模式用）")
    ap.add_argument("--prompt", default=None)
    ap.add_argument("--mode", default="image", choices=["image", "frames"],
                    help="image=普通图片语义理解(默认)；frames=视频抽帧(带时间戳)")
    ap.add_argument("--provider", default="auto", choices=["auto", "magpie", "deepseek"],
                    help="auto=先本机 magpie 网关，再官方 API（默认）")
    args = ap.parse_args()

    chain = providers(args.provider)
    if not chain:
        hint = ("没有可用的视觉通道：magpie 网关不可用，且未设 DEEPSEEK_API_KEY。"
                if args.provider == "deepseek" else
                "没有可用的视觉通道：本机 magpie 网关未运行，也未设 DEEPSEEK_API_KEY。")
        print(json.dumps({
            "success": False, "text": "", "char_count": 0,
            "method": "error", "error": hint,
        }, ensure_ascii=False))
        sys.exit(1)

    times = None
    if args.times:
        times = [t.strip() for t in args.times.split(",") if t.strip()]
    if args.mode == "frames" and not times:
        # frames 模式需时间戳；无则自动生成序号时间
        times = [f"{i}s" for i in range(len(args.images))]

    errors = []
    t0 = time.time()
    for name, model, key in chain:
        log(f"{len(args.images)} 张, mode={args.mode}, detail={args.detail}, provider={name}, model={model}")
        try:
            if name == "magpie":
                r = ask_magpie(args.images, args.detail, times, args.prompt, args.mode)
            else:
                r = ask_deepseek(key, args.images, args.detail, times, args.prompt, args.mode)
            msg = (r["choices"][0]["message"].get("content") or "").strip()
            if not msg:
                raise RuntimeError("模型返回空正文（reasoning 占满了 token？）")
            usage = r.get("usage", {})
            per_image = parse_vision_to_per_image(msg, args.images, times or [""] * len(args.images))
            out = {
                "success": True,
                "text": msg,
                "char_count": len(msg.replace("\n", "").replace(" ", "")),
                "method": f"ds-vision-{name}-{model}-{args.mode}",
                "error": None,
                "usage": usage,
                "per_image": per_image,
                "elapsed_s": round(time.time() - t0, 1),
            }
            print(json.dumps(out, ensure_ascii=False))
            return
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, KeyError,
                ValueError, RuntimeError) as e:
            errors.append(f"{name}: {type(e).__name__}: {str(e)[:160]}")
            continue

    print(json.dumps({
        "success": False, "text": "", "char_count": 0,
        "method": "error",
        "error": "画面语义调用失败（" + "；".join(errors) + "）",
    }, ensure_ascii=False))
    sys.exit(1)


if __name__ == "__main__":
    main()
