#!/usr/bin/env python3
"""
Agent 0 · 采编 — 图片本地 OCR 工具（纯本地，无云端）

对本地图片做中文 OCR，
使用 RapidOCR（onnxruntime），完全离线、数据不出本机。
与视频画面采集（extract-video-frames.py）共用同一套 RapidOCR 后端。

用法：
  python extract-image-ocr.py --input <图片目录 | JSON 清单>
  python extract-image-ocr.py --images img1.png img2.png

依赖：
  pip install rapidocr-onnxruntime   # 需含 rapidocr 的解释器（默认 3.13 无，本机用 ocr venv）

输出 JSON 到 stdout（通用契约 + 扩展）：
  {
    "success": true,
    "text": "<所有图片 OCR 文字合并>",
    "char_count": N,
    "method": "rapidocr-ch",
    "error": null,
    "per_image": [{"file": "images/img_0.png", "text": "..."}, ...]
  }
"""

import argparse
import glob
import json
import os
import sys

IMAGE_EXTS = ('.png', '.jpg', '.jpeg', '.bmp', '.webp')


def log(msg, file=sys.stderr):
    print(f'[ocr] {msg}', file=file)


def collect_images(args):
    """返回 (图片绝对路径列表, 基准目录) —— 用于把相对路径写回结果。"""
    if args.images:
        paths = [os.path.abspath(p) for p in args.images if os.path.isfile(p)]
        return paths, os.getcwd()

    inp = args.input
    if not inp:
        return [], os.getcwd()

    if inp.lower().endswith('.json'):
        with open(inp, 'r', encoding='utf-8') as f:
            data = json.load(f)
        work_dir = data.get('work_dir') or os.path.dirname(os.path.abspath(inp))
        imgs = data.get('images', [])
        paths = [os.path.join(work_dir, p) if not os.path.isabs(p) else p for p in imgs]
        paths = [p for p in paths if os.path.isfile(p)]
        return paths, work_dir

    if os.path.isdir(inp):
        paths = []
        for ext in IMAGE_EXTS:
            paths.extend(glob.glob(os.path.join(inp, f'**/*{ext}'), recursive=True))
        return sorted(paths), inp

    return [], os.getcwd()


def safe_relpath(path, base):
    """跨盘安全的相对路径：同盘给相对路径，异盘退化为文件名（relpath 跨盘会抛 ValueError）。"""
    try:
        return os.path.relpath(path, base).replace('\\', '/')
    except ValueError:
        return os.path.basename(path)


def main():
    parser = argparse.ArgumentParser(description='图片本地 OCR（RapidOCR）')
    parser.add_argument('--input', help='图片目录，或包含图片路径的 JSON 清单')
    parser.add_argument('--images', nargs='+', help='一张或多张图片路径')
    args = parser.parse_args()

    image_paths, base_dir = collect_images(args)
    if not image_paths:
        out = {
            'success': False, 'text': '', 'char_count': 0, 'method': 'error',
            'error': '未找到任何图片：请通过 --input <目录|JSON> 或 --images 指定',
        }
        print(json.dumps(out, ensure_ascii=False))
        sys.exit(1)

    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as e:
        out = {
            'success': False, 'text': '', 'char_count': 0, 'method': 'error',
            'error': f'rapidocr-onnxruntime 未安装: pip install rapidocr-onnxruntime。{e}',
        }
        print(json.dumps(out, ensure_ascii=False))
        sys.exit(1)

    log(f'初始化 RapidOCR（CPU）... 首次会下载模型')
    try:
        ocr = RapidOCR()
    except Exception as e:
        out = {
            'success': False, 'text': '', 'char_count': 0, 'method': 'error',
            'error': f'RapidOCR 初始化失败: {e}',
        }
        print(json.dumps(out, ensure_ascii=False))
        sys.exit(1)

    per_image = []
    combined = []
    for img in image_paths:
        try:
            rel = safe_relpath(img, base_dir)
            result, _ = ocr(img)
            lines = [item[1] for item in result] if result else []
            text = '\n'.join(l for l in lines if l and l.strip())
        except Exception as e:
            log(f'OCR 失败 {img}: {e}')
            rel = safe_relpath(img, base_dir)
            text = ''
        per_image.append({'file': rel, 'text': text})
        if text:
            combined.append(f'### 图片 {rel}\n{text}')

    full_text = '\n\n'.join(combined)
    out = {
        'success': True,
        'text': full_text,
        'char_count': len(full_text.replace('\n', '').replace(' ', '')),
        'method': 'rapidocr-ch',
        'error': None,
        'per_image': per_image,
    }
    print(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()
