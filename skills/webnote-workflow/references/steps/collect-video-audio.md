# 采编 · 视频 / 音频

> 分支卡。由调度器在判断为视频或音频后加载，配合 `skills/video-extract/` 使用。

## 三级策略（按顺序，够了就停）

### 第一步：页面文本（秒级，零依赖）

```bash
python tools/extract-video-text.py <URL>
```

取标题、描述、评论。**有 URL 就先跑这一步**，成本最低。

### 第二步：语音 ASR（分钟级，需模型）

**页面文本不足（< 200 字符）时**才走这步：

```bash
python tools/extract-video-asr.py <URL 或 --input 本地视频>
```

依赖：`yt-dlp`、`faster-whisper`、`ffmpeg`。

### 第三步：画面采集（可选，需 Key）

仅当视频是**教程 / 课程 / 录屏 / 演示类**——画面含提示词原文、界面文字、操作步骤，且这些是语音转写覆盖不到的。

```bash
python tools/extract-video-frames.py --input <本地视频> \
  [--t-start S] [--t-end S] [--max-frames N] [--out result.json]
```

链路：`ffmpeg` 抽帧（5s 周期 + 场景帧）→ `RapidOCR` 逐帧文字 → `ds_vision.py` 每 14 帧一批语义 → 按时间戳对齐。

依赖：`ffmpeg`、`rapidocr-onnxruntime`、`DEEPSEEK_API_KEY`。

## 触发规则（重要）

**Agent 无法判断某视频是否属于"教程/录屏类、画面含文字"时，必须询问用户**，不得擅自决定执行或跳过。

只有能确定画面含有效文字信息时才自动启用第三步，否则停在第二步。

理由：这一步会花 token 和时间。擅自跑是浪费，擅自跳过可能丢掉教程类视频最核心的信息——而这两者你从标题上都看不出来。

## 输出处理

- `per_frame[]` 里每帧有 `t / ocr_text / vision_text`，**语音与画面要分开存**
- 正文字符数记总长度；原文来源指向 `frames_output.json`（或 `--out` 指定的文件）
- 在采编说明里写清**实际执行了哪几步、跳过了哪几步、为什么**

## 已知坑

- **时间戳**：抽帧带 `-ss t_start` 后帧时间是相对值，工具已修正为绝对视频时间
- **OCR 界面噪声**：WPS 工具栏等菜单词会被整段抓入，属正常现象，不要当作内容
- **本地小 VLM 不可行**（无独显单帧 110s+），云端 Vision 快约 100 倍
- **跨盘符问题**：`extract-image-ocr.py` 在 Windows 下图片与 cwd 不同盘符时 `os.path.relpath` 会抛 `ValueError`。规避：在目标盘符目录下执行再指回脚本路径
