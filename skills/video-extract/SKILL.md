---
name: video-extract
description: 从视频中提取"内容"（页面文本 + 语音 ASR + 画面语义/文字）。当用户提供视频（本地文件或链接），需要"视频讲了什么 + 画面上的文字/界面"时使用。链路：extract-video-text(页面文本) → extract-video-asr(语音) → extract-video-frames(抽帧 + RapidOCR 文字 + DeepSeek Vision 语义)。依赖：ffmpeg、faster-whisper、RapidOCR、DEEPSEEK_API_KEY。
agent_created: true
---

# 视频内容提取（Video → 语音 + 画面文字/语义）

> 本 skill 是 WebNote 项目的一部分，工具随项目内置在 `tools/`。

## 何时使用

- 用户给一个视频（本地文件或链接），说"看这个视频，把内容/提示词/步骤提取出来"
- 处理教程、课程、PPT 录屏、代码演示类视频，需要**语音** + **画面上的文字和界面**
- 作为"网页内容 → md"流程中视频素材的处理

## 核心理念

1. **三种信息源互补，缺一不可**：
   - `extract-video-text`：页面标题/描述/评论（秒级，零依赖）
   - `extract-video-asr`：语音转写（口播说了什么）
   - `extract-video-frames`：画面文字（OCR）+ 画面语义（Vision）——教程/录屏类视频价值常在这
2. **OCR 管文字，Vision 管语义**：RapidOCR 逐字准确，DeepSeek Vision 懂"画面在讲什么"。两者按时间戳交叉校验。
3. **DeepSeek Vision 不支持视频**，只收图片。"先抽帧再批量送图"是唯一路径（每 14 帧一批）。
4. **看不清标 [?]，不编造**。

## 直接用内置工具

```bash
# 前置（画面语义需 Key；ASR 语音与 OCR 文字纯本地）
export DEEPSEEK_API_KEY="sk-xxx"

# 1) 页面文本（若有 URL）：extract-video-text.py <URL>
# 2) 语音转写（本地视频或 URL）：
python tools/extract-video-asr.py --input video.mp4

# 3) 画面提取（抽帧 → OCR 文字 → Vision 语义 → 时间戳对齐）：
python tools/extract-video-frames.py --input video.mp4 \
  [--t-start S] [--t-end S] [--max-frames N] [--out result.json]
```

- `extract-video-frames.py` 输出统一 JSON：`{success, text(Markdown), per_frame[{file,t,ocr_text,vision_text}]}`
- 完整用法见 `tools/README.md`「画面采集工具说明」章节。

## 处理步骤（完整流程）

1. **判断是否需要**：画面含文字/界面信息（教程/录屏/演示）→ 跑画面提取；纯口播 → 仅 ASR 即可。
2. **页面文本**：`extract-video-text <URL>`（如有链接）。
3. **语音 ASR**：`extract-video-asr --input <视频>`。
4. **画面提取**：`extract-video-frames --input <视频>`（内部：ffmpeg 抽帧场景+5s → RapidOCR 文字 → ds_vision 14帧/批语义 → 时间戳对齐）。
5. **合并**：页面文本 + 语音 + 画面文字/语义，按需产出 md。

## 关键参数（防幻觉，必须保留）

- `reasoning_effort:"none"` + `detail:"high"`（ds_vision 内部已固定）。
- 每 14 帧一批（规避 48MiB 请求体上限与 ≥15 图尺寸下降）。

## 经验与坑

- **时间戳**：抽帧带 `-ss t_start` 后帧时间是相对值，工具已修正为绝对视频时间。
- **Key 安全**：用环境变量 `DEEPSEEK_API_KEY`，绝不进代码/git。
- **OCR 界面噪声**：WPS 工具栏等菜单词会被整段抓入，可后处理过滤。
- **本地小 VLM 不可行**（无独显单帧 110s+）；云端 Vision 快 ~100 倍且更准。
