---
name: xhs-note
description: 处理小红书（XHS）笔记到本地 Markdown 的完整流水线。当用户提供小红书链接/note_id，需要把图文笔记（文字 + 图片 OCR + 视频 ASR）整理成可本地保存的 md 文档时使用。链路：extract-xhs(拉取+落盘) → extract-image-ocr(图片文字) → extract-video-asr(视频语音) → 组装 note.md。依赖：xhs, requests, RapidOCR, faster-whisper, XHS_COOKIE（登录态）。
agent_created: true
---

# 小红书笔记 → 本地 Markdown（XHS 流水线）

> 本 skill 是 WebNote 项目的一部分，工具随项目内置在 `tools/`。

## 何时使用

- 用户给一个小红书链接或 note_id，说"把这个笔记整理成本地文档"
- 处理小红书图文笔记（需图片 OCR）或视频笔记（需视频 ASR）
- 纯本地离线，数据不出本机；唯一外部依赖是拉取用的小红书登录 Cookie

## 关键点

- **纯本地**：图片/视频为公开 CDN，无需 Cookie；仅 API 拉取 note_card 需要登录态。
- **Cookie 反爬**：小红书反爬依赖登录态签名，Cookie 过期会返回 SignError / IPBlockError，需手动更新。
- **OCR 后端**：现统一为 RapidOCR（不再用 PaddleOCR 的 3.11 venv）。

## 直接用内置工具

```bash
# 0) 准备 Cookie（三选一）
#    a. 环境变量： export XHS_COOKIE="a1b2...; web_session=..."
#    b. 同目录 cookie.txt
#    c. 命令行 --cookie "..."
#
# 1) 一条命令跑完整流水线（推荐）：
python tools/run-xhs-note.py "https://www.xiaohongshu.com/explore/<note_id>" \
  [--out <目录>] [--cookie "..."] [--asr-model large-v3-turbo]

# 或分步：
python tools/extract-xhs.py <URL>          # 拉取 + 下载图片/视频到 work_dir
python tools/extract-image-ocr.py --input <fetch.json>   # 图片 OCR
python tools/extract-video-asr.py --input <video>        # 视频 ASR
```

- 产出 `<work_dir>/note.md`：自包含 Markdown（标题/描述/标签/逐图OCR/视频转写）。
- `run-xhs-note.py` 输出：`{success, note_md, work_dir, ...}`。

## 依赖

```bash
pip install xhs requests
pip install rapidocr-onnxruntime   # OCR：需含 rapidocr 的解释器（默认 3.13 无，建议独立 venv）
# ASR: faster-whisper + ffmpeg（项目已有）
```

## 经验与坑

- **Cookie 过期**：触发风控返回 SignError / IPBlockError，需换新 Cookie。
- **OCR 后端**：extract-image-ocr.py 已从 PaddleOCR 切换为 RapidOCR，与视频画面采集统一。
- **图片艺术字/手写体**：OCR 可能漏识，纯本地无云端兜底。
- **视频转写为语音**：不含画面文字；如需画面内容，用 video-extract skill 的 extract-video-frames。
