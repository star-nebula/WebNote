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
| 图文（正文为空） | `extract-webpage.py <URL>`（BrowserSkill） | — |
| 文档 | `extract-document.py <文件路径>` | — |
| 图片 | OCR →（可选）Vision | [collect-image.md](collect-image.md) |
| 视频 / 音频 | 页面文本 → ASR → 画面 | [collect-video-audio.md](collect-video-audio.md) |
| 小红书 | `run-xhs-note.py <URL>`（需 Cookie） | 加载 `skills/xhs-note/` |
| 无法判断 | `extract-webpage.py <URL>` 尽力读取 | — |

**只加载命中的分支卡。** 处理一个 PDF 时不需要知道 ASR 怎么跑。

## 工具输出格式

统一 JSON 到 stdout，取 `text` 字段：

```json
{"success": true, "text": "...", "char_count": 1234, "method": "pypdf|bsk-webpage|bsk-video|faster-whisper-small|video-frames-rapid+ds-vision", "error": null}
```

`extract-video-frames.py` 另输出 `per_frame[]`（每帧 `file / t / ocr_text / vision_text`）。

## 铁律

- 通过 BrowserSkill 操作**用户已登录的浏览器**读取页面，不发起未经认证的 HTTP 请求
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
```

**清单只记路径和元信息，不存正文。** 归类师和笔记匠按「原文来源」列去读原始文件。

> 注意：「内容要点」是给归类师的路标，不是笔记。别在这里写得太详细，否则后面的 agent 会照抄你的概括而不是去读原文。
