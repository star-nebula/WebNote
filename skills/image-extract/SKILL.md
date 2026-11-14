---
name: image-extract
description: 从图片中提取"内容"（OCR 逐字文字 + 画面语义理解）。当用户提供一张或多张图片（截图、海报、文档扫描、UI 界面等），需要"图片里有什么文字 + 图片在讲什么内容/场景"时使用。纯本地 OCR（RapidOCR）管文字，可选云端 DeepSeek Vision 管画面语义。依赖：RapidOCR；画面语义走本机 magpie 网关，或 DEEPSEEK_API_KEY。
agent_created: true
---

# 图片内容提取（Image → 文字 + 语义）

> 本 skill 是 WebNote 项目的一部分，工具随项目内置在 `tools/`。

## 何时使用

- 用户给一张或多张图片，说"看看图里有什么 / 图里写了什么 / 这是什么界面"
- 处理截图、海报、扫描件、UI 界面、图表，需要提取文字 + 理解内容
- 作为"网页内容 → md"流程中图片素材的处理环节

## 核心理念

1. **OCR 管文字，Vision 管语义，两者互补**：RapidOCR 逐字提取（准确），DeepSeek Vision 理解"这是什么内容/场景"（语义）。OCR 读小字准但认不出画面意思，Vision 懂语义但小字会错。
2. **纯本地 OCR 保底**：RapidOCR 完全离线，文字提取不依赖网络。云端 Vision 仅用于"画面语义理解"，可选。
3. **看不清标 [?]，不编造**：Vision 输出要求对无法辨认的文字标注，不臆测。

## 直接用内置工具

```bash
# 前置：画面语义默认走本机 magpie 网关（无需 Key）
# 网关不可用时才用官方通道：export DEEPSEEK_API_KEY="sk-xxx"

# 1) 本地 OCR：逐字文字（纯本地，无 Key 也能用）
python tools/extract-image-ocr.py --images img1.png img2.jpg      # 指定图片
python tools/extract-image-ocr.py --input <图片目录|JSON>          # 目录或清单 JSON

# 2) 云端 Vision：画面语义理解（可选；magpie 网关或 Key）
python tools/ds_vision.py img1.png img2.jpg --mode image

# 组合：OCR 文字 + Vision 语义
```

- `extract-image-ocr.py` 输出：`{success, text, method:"rapidocr-ch", per_image[{file,text}]}`
- `ds_vision.py` 输出：`{success, text, method:"ds-vision-...-image", per_image[{file,t,text}]}`
- 完整用法见 `tools/README.md` 与各工具头部注释。

## 处理步骤

1. **收集图片**：`extract-image-ocr.py --images <图1> <图2>...` 或 `--input <目录/JSON>`。
2. **OCR 文字**：RapidOCR 一次初始化循环所有图片（进程内复用），逐字提取。
3. **（可选）语义理解**：`ds_vision.py <图...> --mode image` 理解画面内容/场景/主要文字摘录。
4. **合并**：OCR 文字（准确）+ Vision 语义（画面在讲什么），按图对齐。

## 关键参数（防幻觉，必须保留）

- `reasoning_effort:"none"` —— 否则模型思考占满 max_tokens，正文返回空。
- `detail:"high"` —— `low` 压图到 512×512 会诱发严重幻觉。
- 一次请求 ≤600 图、单图 ≤384 token；大批量分 14 张/批。

## 经验与坑

- **Key 安全**：官方通道用环境变量 `DEEPSEEK_API_KEY`，绝不写进代码/git；magpie 网关走本机路由，不落 Key。
- **OCR 界面噪声**：截图里的工具栏/菜单词会被整段抓入，可后处理过滤，但保留原文更安全。
- **本地小 VLM 不可行**（无独显单帧 110s+）；云端 Vision 快且准。
