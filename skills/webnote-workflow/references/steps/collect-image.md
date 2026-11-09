# 采编 · 图片 / 截图

> 分支卡。由调度器在判断为图片后加载，配合 `skills/image-extract/` 使用。

## 两步策略

### 第一步：OCR 逐字文字（本地，零依赖，默认必跑）

```bash
python tools/extract-image-ocr.py --images <图片路径...>
```

RapidOCR 提取画面上**实际写着什么**。逐字可靠，但可能误识别（形近字、艺术字、低分辨率）。

### 第二步：Vision 画面语义（云端，需 Key，按需）

```bash
python tools/ds_vision.py <图片路径...> --mode image
```

DeepSeek Vision 理解**画面在讲什么**。能补上 OCR 抓不到的语义，但它是**模型产出**，不是原文。

## 什么时候跑第二步

| 情况 | 建议 |
|---|---|
| 截图、界面、文档扫描、含文字的图 | OCR 通常够用，Vision 可选 |
| 照片、示意图、图表、无文字图 | **必须跑 Vision**，否则拿不到任何内容 |
| 拿不准 | 问用户 |

## 关键：两类产物必须分开存

OCR 文字和 Vision 描述**不能混成一段**。

理由：核查官要靠这个区分证据强度——OCR 逐字至少是"画面上确实印着这些字"，而 Vision 描述是模型对画面的理解。混在一起，核查官就无法判断一条要点到底有没有落到实处的依据，只能一律标"已核实"，那这张图进知识库就是隐性风险。

存的时候分开两段，各自标明：

```markdown
### OCR 逐字文字
<RapidOCR 输出原文>

### Vision 画面语义
<DeepSeek Vision 输出>
```

## 已知坑

- **看不清就标 `[?]`，不编造**——这是 `skills/image-extract/` 的硬规则
- **跨盘符问题**：Windows 下图片与 cwd 不同盘符时 `os.path.relpath` 会崩溃，规避方法见 [collect-video-audio.md](collect-video-audio.md) 的已知坑
- Vision 参数 `reasoning_effort:"none"` + `detail:"high"` 已在 `ds_vision.py` 内部固定，不要改
