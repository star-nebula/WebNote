---
step: 1
executor: 调度器
context: none
reads:
  - 用户给定的 URL / 本地文件 / 浏览器剪藏
forbidden:
  - 改写、移动或删除原始输入
  - 绕过付费墙或登录墙
writes:
  - runs/<run>/00-采编清单.md
produces: 00-采编清单.md
format_needles:
  - '| ID | 标题 | 域名 | 媒体格式 | 正文字符数 | 有正文 | 提取方式 | 提取结果 | 原文来源 |'
  - '## 运行异常'
---

# 采编（调度器自执行）

> 产出：`runs/<run>/00-采编清单.md`

> 本文件是操作卡，不是 agent。由**调度器（主会话）**执行，不创建独立上下文。

## 职责

把各种来源的内容变成**可核查的文本**，并记录来源路径。只提取，不生成、不总结、不补充。

## 媒体格式判断（优先级由高到低）

1. **文件扩展名**：路径末尾（不含查询参数）以 `.pdf/.docx/.pptx/.xlsx` 结尾 → **文档**
2. **域名 + 路径模式**：
   - 音频：`music.163.com`、`music.youtube.com`、`spotify.com`、`xiaoyuzhoufm.com`、`podcasts.apple.com`
   - 视频：`youtube.com/watch`、`youtu.be`、`bilibili.com/video`、`b23.tv`、`douyin.com`、`kuaishou.com`、`v.qq.com`、`v.youku.com`、`iqiyi.com`
   - 图文：`mp.weixin.qq.com`、`zhuanlan.zhihu.com`、`blog.csdn.net`、`juejin.cn`、`oschina.net`、`segmentfault.com`、`medium.com`
3. **路径模式**：含 `/article/`、`/posts/`、`/blog/` 等 → **图文**
4. **都判断不了** → 标「无法判断」，**问用户**，不硬猜

## 路由：判断完加载对应的分支卡

| 判断结果 | 处理方式 | 分支卡 |
|---|---|---|
| 图文（已有正文） | 直接使用，不调工具 | — |
| 图文（正文为空） | `extract-webpage.py <URL>`（走 `bsk`，需在 PATH 上） | — |
| 文档 | `extract-document.py <文件路径>` | — |
| 图片 | OCR →（可选）Vision | [branches/image.md](branches/image.md) |
| 视频 / 音频 | 页面文本 → ASR → 画面 | [branches/video-audio.md](branches/video-audio.md) |
| 防复制页 / 云文档 / 登录墙长文 | PowerShell + Chrome 链无损拓存 | [branches/web-archive.md](branches/web-archive.md) |
| 无法判断 | `extract-webpage.py <URL>` 尽力读取 | — |

**只加载命中的分支卡。** 处理一个 PDF 时不需要知道 ASR 怎么跑。

## 工具输出格式

统一 JSON 到 stdout，取 `text` 字段：

```json
{"success": true, "text": "...", "char_count": 1234, "method": "pypdf|bsk-webpage|bsk-video|faster-whisper-small|video-frames-rapid+ds-vision", "error": null}
```

`extract-video-frames.py` 另输出 `per_frame[]`（每帧 `file / t / ocr_text / vision_text`）。

## 铁律

- 通过 `bsk`（BrowserSkill）操作**用户已登录的浏览器**读取页面，不发起未经认证的 HTTP 请求
- 只提取已有文本，不生成、不总结、不补充
- 提取失败如实标「无法提取」，不硬凑
- `DEEPSEEK_API_KEY` 只走环境变量，不进代码、不进 git
- 原文**只读**，不复制、不移动

## 输出 → `runs/<run>/00-采编清单.md`

```markdown
# 00-采编清单

> 生成时间：<日期>
> 执行者：调度器（主会话）
> 运行模式：模式 A / 模式 B

## 内容清单

| ID | 标题 | 域名 | 媒体格式 | 正文字符数 | 有正文 | 提取方式 | 提取结果 | 原文来源 |
|----|------|------|---------|-----------|--------|---------|---------|---------|
| p01 | ... | ... | 图文 | 807 | 有 | 直接使用剪藏正文 | 成功 | `<路径>` |

## 逐条采编说明

### p01 · <标题>
- 来源类型：<...>
- 处理方式：<...>
- 内容要点：<一句话概括，供归类师参考>

## 分类汇总（供 01 使用）

- 有正文：N 条
- 无正文：M 条

## 运行异常

- <哪一步 · 什么现象 · 当时怎么处理的>（无异常写「无」）
```

**清单只记路径和元信息，不存正文。** 归类师和笔记匠按「原文来源」列去读原始文件。

## 运行异常：这是改进流程的唯一入口

运行中出错的地方写进这一节，**不要只在对话里吐槽**：工具报错、参数踩坑、人工补救、绕过的步骤、预期外的时间与 token 消耗。

- 有异常就逐条写清「哪一步 · 什么现象 · 当时怎么处理的」，没有就写「无」。
- 这一节留给**过程**，不写结论：值不值得改流程，看它出现几次。
- 同一异常**第二次**出现时，必须升级——变成一条测试（首选，红了就非修不可）或一条 `docs/decisions.md`，而不是继续堆在这里。

判据：写在这里的东西，下一次运行的人（可能是你自己）会读到；写进别处的，就没人读了。
