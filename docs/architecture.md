# 网页笔记工作流

> **版本：v3（现行）。** v1「四步工作流」（2026-07-14）与 v2「五个 Agent 减到三个」（2026-08-04）见 [`versions/`](versions/)，版本关系见 [`docs/README.md`](README.md)。本文与代码同源，改流程只改这里。

把"内容采集 → 整理分类 → 提炼笔记 → 确认发布"拆成**调度器（主会话） + 三个独立 Agent** 分工协作。

不是每一步都需要独立的 AI 上下文。确定性的事调度器（主会话）自己干，只有真正需要独立判断的才交给 subagent。

## 架构总览

```
调度器（主会话）
├── 1. 采编（主会话自己做——确定性逻辑）
│      读 skills/webnote-workflow/references/steps/collect.md，按媒体类型路由，只加载命中的分支卡
│      → 产出 00-采编清单.md
│
├── 2. 创建 subagent：归类师 ← 独立上下文
│      读 agents/classifier.md
│      四选一语义分类
│      → 产出 01-整理清单.md
│
├── 3. 创建 subagent：笔记匠 ← 独立上下文
│      读 agents/distiller.md
│      每条要点标注出处与来源类型
│      → 产出 02-笔记.md
│
├── 4. 创建 subagent：核查官 ← 全新上下文，必须独立
│      读 agents/verifier.md
│      逐条比对，三态判定
│      → 产出 03-核查表.md
│
└── 5. 确认（主会话自己做——汇总+约束）
       读 skills/webnote-workflow/references/steps/confirm.md
       → 产出 04-待确认提案.md（全部停在"待确认"）
```

**为什么有些步骤不是独立 Agent：**

| 步骤 | 是否独立 | 理由 |
|------|---------|------|
| 采编 | ❌ 主会话内化 | URL 分类用规则，文本提取调用 CLI 工具——都是确定性逻辑，不需要 AI。AI 做反而可能猜错 |
| 归类师 | ✅ 独立 | 四选一分类需要理解正文语义，归类师的判断不应影响笔记匠 |
| 笔记匠 | ✅ 独立 | 提炼是核心创作任务，需要完整上下文专注正文 |
| 核查官 | ✅ **必须独立** | 这是安全闸门。笔记匠自己核查自己等于自检——它查不出自己刚才编了什么 |
| 确认 | ❌ 主会话内化 | 不读原文、不做新判断，只是汇总前三个产出 + 约束落地行为。确定性逻辑 |

---

## 五步索引

细节全部在对应文件里，**这里是索引，不是复述**：

| 步 | 产物 | 执行者 | 定义文件 |
|---|------|--------|---------|
| 1 采编 | `00-采编清单.md` | 调度器 | [steps/collect.md](../skills/webnote-workflow/references/steps/collect.md) |
| 2 归类师 | `01-整理清单.md` | subagent | [agents/classifier.md](../agents/classifier.md) |
| 3 笔记匠 | `02-笔记.md` | subagent | [agents/distiller.md](../agents/distiller.md) |
| 4 核查官 | `03-核查表.md` | subagent（全新） | [agents/verifier.md](../agents/verifier.md) |
| 5 确认 | `04-待确认提案.md` | 调度器 | [steps/confirm.md](../skills/webnote-workflow/references/steps/confirm.md) |

每个 agent 定义文件的头部有 frontmatter 契约（`context` / `reads` / `writes` / `forbidden`）。派发规则见 [skills/webnote-workflow/SKILL.md](../skills/webnote-workflow/SKILL.md)。

## 两条关键设计

### 一、来源类型贯穿全流程

笔记匠给每条要点标注来源类型（`原文` / `OCR` / `ASR` / `Vision`），核查官据此判定证据强度。**这两个 agent 之间靠这个标记交接**，它是整套流程可信度的基础。

没有这个标记，核查官只能一律标"已核实"——那么一条来自 OCR 误识别的数字，会和 PDF 里的白纸黑字获得同样的可信度。

### 二、核查是三态，不是两态

| 状态 | 含义 |
|---|---|
| 已核实（直接引用） | 出处在原文中存在，可定位 |
| 已核实（转述源） | 出处在 OCR/ASR/Vision 产出中存在，但未回溯原始音画 |
| 可疑 / 原文无依据 | 找不到出处，或表述超出原文 |

判据与真实案例见 [agents/verifier.md](../agents/verifier.md)。

---

## 三条不可逾越

1. **正文不凭空编** —— 文本来自工具提取或用户已有，没有就如实写"无"
2. **核查独立** —— 核查者不能是笔记的撰写者（`context: fresh`，全新上下文）
3. **落地必待确认** —— 所有删除/归档/发布/写入长期记录的动作停在"待确认"，用户逐条点头才执行

---

## 跨工具使用

### 方式一：装配 skill（推荐）

把项目内 `skills/` 装进你的 AI 工具，之后自然对话即触发。

- WorkBuddy / Codex：`项目/skills/` → `.workbuddy/skills/`、`.codex/skills/`
- Claude Code：`项目/skills/` → `.claude/skills/`
- 不支持项目级 skill 的工具：走方式二

> **注意**：`skills/webnote-workflow/SKILL.md` 是总路由卡；`skills/web-archive/SKILL.md` 承载防复制页、云文档和懒加载长文的无损拓存分支。角色定义（`agents/`）、步骤卡（`skills/webnote-workflow/references/steps/`）与工具（`tools/`）是流程资产，归项目根。SKILL.md 第一步会先定位项目根（判定标准是目录下同时存在 `docs/architecture.md` 和 `tools/`），所以**完整流程必须在项目根工作区内运行**。若想在某工具里把角色注册成可复用的 subagent，把 `.claude/agents/` 里对应薄壳复制到该工具的注册位。

### 方式二：一条提示词（不装配也能用）

把 [`AGENTS.public.md`](../AGENTS.public.md) 与内容一起交给 AI——它本身就是入口说明，含角色清单、可写范围与执行规则。

没有 subagent 能力的聊天界面，改用模式 B 的三段式提示词：[`degraded-single-dialog.md`](../skills/webnote-workflow/references/degraded-single-dialog.md)。

### 方式三：手动文件流水线

按五步顺序，每次让 AI 读对应的定义文件。采编和确认由你手动串起来。

每次运行在 `runs/` 下建子目录 `YYYY-MM-DD-主题`，五个输出文件并列写入。原文不复制、不移动，仅记录来源路径。多次运行互不覆盖。

完整范例见 [`examples/`](../examples/)。

---

## 一句话纪律

**AI 可以无限地"想"和"建议"，但凡要"落地动手"，停在你这道闸前。**

---

> 设计参考：[Agent OS 的第一课：会分工，才会用 Agent](https://www.axtonliu.ai/newsletters/ai-2/posts/agent-os-workstation-division)（分工隔离、独立核查、确认闸门三层设计）
> 工具依赖：BrowserSkill（浏览器操作）见 [docs/BrowserSkill 安装指南](vendor/BrowserSkill%20Installation%20Guide.md)，命令参考见 [docs/BrowserSkill 命令参考](vendor/BrowserSkill%20Command%20Reference.md)
