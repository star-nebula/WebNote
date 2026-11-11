# Agent 0 · 采编 工具集

统一 CLI 接口，供调度器（主会话）调用的文本提取工具。

## 新工具的最低要求

三条，都有测试盯着，别绕：

1. **能导入**——`runpy.run_path(path, run_name='probe')` 不报错（顶层 import 不许死、模块级不许抛）
2. **`--help` 能跑**——有 `argparse` 的必须支持，且输出含 `usage`（参数冲突、`dest` 拼错只在解析时炸）
3. **输出 JSON 五个键**——见下；失败分支也一样（`tests/test_repo.py` 对 7 个提取工具逐个断言，新增工具要在 `EXTRACTOR_CASES` 里补一行，否则测试直接红）

## 输出格式（所有工具通用）

所有工具输出 JSON 到 stdout：

```json
{
  "success": true,
  "text": "提取到的文本内容...",
  "char_count": 1234,
  "method": "pypdf / python-docx / bsk-webpage / bsk-video / faster-whisper-small / error",
  "error": null
}
```

失败时：

```json
{
  "success": false,
  "text": "",
  "char_count": 0,
  "method": "error",
  "error": "错误描述"
}
```

## 工具列表

| 工具 | 用途 | 依赖 | 速度 |
|------|------|------|------|
| `extract-document.py <文件路径>` | 从 PDF/DOCX 提取文本 | pypdf, python-docx | 秒级 |
| `extract-webpage.py <URL>` | 通过 BrowserSkill 读取图文页面 | bsk CLI | 秒级 |
| `extract-video-text.py <URL>` | 通过 BrowserSkill 读取视频页面文本 | bsk CLI | 秒级 |
| `extract-video-asr.py <URL\|--input 本地文件> [--model small\|large-v3-turbo] [--max-duration N]` | 下载视频音频（或读本地文件）并用 ASR 转写语音 | yt-dlp, faster-whisper, ffmpeg | 分钟级 |
| `extract-video-frames.py --input <本地视频> [--t-start S] [--t-end S] [--max-frames N]` | **视频画面采集**：抽帧 + 本地 RapidOCR 取逐字文字 + 云端 DeepSeek Vision 理解画面语义，按时间戳对齐 | ffmpeg, rapidocr-onnxruntime, DEEPSEEK_API_KEY | 分钟级 |
| `ds_vision.py <图片...> [--times ...]` | 单批图片送 DeepSeek Vision 理解（被 extract-video-frames 内部调用，每 14 帧一批） | DEEPSEEK_API_KEY | 秒级 |
| `extract-image-ocr.py --input <目录\|JSON>` | 对图片做本地 OCR（RapidOCR，与视频画面采集统一后端） | rapidocr-onnxruntime | 秒~分钟级 |

## 自检与维护

| 工具 | 用途 | 依赖 | 进 CI |
|---|---|---|---|
| `check-env.py` | 当前机器能跑哪些媒体分支、缺什么怎么补 | 无 | 否 |
| `check-links.py` | 全仓 Markdown 相对链接 | 无 | 是 |
| `check_vendor.py [--online]` | 外部技能副本是否还是上游那份 | `gh` 或 `GITHUB_TOKEN`（仅 --online） | 是（离线） |
| `validate_run.py [--all\|runs/<run>/]` | 一份 run 的四份产物是否自洽：条数、条目号连续、三态与来源类型组合、提案是否把每条都归了节 | 无 | 是（CI 里没有 runs/，秒过） |

两个纯函数模块，被工具和测试共同引用，不要各写一份：

| 模块 | 提供什么 | 为什么单独存在 |
|---|---|---|
| `naming.py` | `landing_name()`：三档升级（原标题 → 加作者与平台 → 加日期）、非法字符净化 | 落库命名是唯一会碰到真实文件的规则，写错了要么覆盖笔记、要么生成 Windows 不接受的名字 |
| `safe_path.py` | `safe_relpath()`：同盘给相对路径，跨盘退化为文件名 | `os.path.relpath` 跨盘符抛 `ValueError`，2026-11 真崩过一次 |

`_migrations/` 里是已跑过的一次性脚本，不进运行时。

## ASR 工具说明

`extract-video-asr.py` 用于需要视频**语音内容**的场景（页面文本不足以覆盖视频实际讲的内容）。

**工作流程**：

```
yt-dlp 下载音频 -> ffmpeg 转为 16kHz WAV -> faster-whisper 转写 -> 带时间戳的文本
```

**模型选择**：

| 模型 | 大小 | CPU 速度 | 精度 | 适用场景 |
|------|------|---------|------|---------|
| `small` | 464MB | ~4x 实时 | 中 | 快速预览、短视频 |
| `large-v3-turbo` | ~800MB | ~1.5x 实时 | 高 | 正式笔记、长视频 |

**参数**：

```
python extract-video-asr.py <URL>
  --model small|medium|large-v3-turbo   # 默认 large-v3
                                        # large-v3-turbo 上游已私有化，未授权时下载会 401
  --max-duration <分钟>                  # 默认 30，超时跳过
  --language zh|auto                     # 默认 zh（简体中文）
```

**输出示例**：

```
[0.0s-3.4s] 这将音乐学院23个研究室改革
[3.4s-9.0s] 来看看这个飞拳飞拳指
...
```

每段带时间戳，便于定位。

**注意事项**：
- 首次运行会自动下载模型（需联网，默认使用 hf-mirror.com 镜像）
- CPU 模式使用 int8 量化，无需 GPU
- 输出为简体中文（通过 initial_prompt 引导）
- 超过 `--max-duration` 的视频会跳过，避免长时间等待

---

## 画面采集工具说明（extract-video-frames.py）

`extract-video-frames.py` 用于**画面含文字/语义信息**的视频（教程、课程、PPT 录屏、代码演示等）——这类视频的价值常在画面上（提示词原文、界面文字、操作步骤），ASR 语音转写覆盖不到。

> 📌 配套 skill 见项目根 `skills/`：`video-extract/`（视频，本工具所在）、`image-extract/`（图片）。含触发判断、处理步骤、坑，接入 AI 时按内容类型加载对应 skill。

**工作流程**：

```
ffmpeg 抽帧（场景变化 + 每5秒定时兜底）
  -> 本地 RapidOCR 逐帧提取逐字文字（管"准确文字"，纯本地不出机）
  -> 云端 DeepSeek Vision 理解画面语义（管"画面在讲什么"，每 14 帧一批）
  -> 按时间戳对齐 -> 统一 JSON + Markdown
```

**用法**：

```bash
# 环境变量提供 Key（绝不写进代码/git）
export DEEPSEEK_API_KEY="sk-xxx"

# 对视频 125s-325s 段做画面采集
python extract-video-frames.py --input video.mp4 --t-start 125 --t-end 325

# 整段 + 限制最多 30 帧
python extract-video-frames.py --input video.mp4 --max-frames 30

# 输出到文件
python extract-video-frames.py --input video.mp4 --out result.json
```

**关键设计**：
- **OCR 管文字 + Vision 管语义的分工**：RapidOCR 逐字提取（准确），DeepSeek Vision 理解界面/场景/阶段（语义）。两者互补——Vision 读小字可能错，OCR 认不出画面意思。
- **每 14 帧一批送 Vision**：规避 48MiB 请求体上限与 ≥15 图时单边尺寸下降。
- **防幻觉两个必留参数**：`reasoning_effort:none`（否则思考占满 max_tokens 正文返回空）、`detail:high`（`low` 压图诱发幻觉）。
- **DeepSeek Vision 不支持视频**，只收图片（JPEG/PNG/GIF/WebP），因此"先抽帧再批量送图"是唯一路径。

**依赖**：
- ffmpeg（系统已装）
- RapidOCR（建议独立 venv：`pip install rapidocr-onnxruntime`；若不在默认解释器，用 `--ocr-python <解释器路径>` 或环境变量 `OCR_PYTHON` 指定）
- DeepSeek API Key（环境变量 `DEEPSEEK_API_KEY`）

**输出 JSON 契约**（通用契约 + 扩展）：
```json
{"success": true, "text": "<Markdown>", "char_count": N,
 "method": "video-frames-rapid+ds-vision", "error": null,
 "frame_count": N, "per_frame": [{"file": "...", "t": 125.0, "ocr_text": "...", "vision_text": "..."}]}
```

**已知限制**：
- 依赖网络（云端 Vision）与 DeepSeek API Key；Key 缺失或网络失败时整工具报错，可降级只用本地 OCR（文字仍可用，语义缺失）。
- 图片会送云端（DeepSeek），敏感视频请评估后再用。

---

