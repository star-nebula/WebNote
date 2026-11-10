# 网页笔记工作流

> **版本：v3（现行）。** v1「四步工作流」（2026-07-14）与 v2「五个 Agent 减到三个」（2026-08-04）见 [`versions/`](versions/)，版本关系见 [`docs/README.md`](README.md)。本文解释为什么这样切分；**流程的唯一定义在 [`skills/webnote-workflow/steps/`](../skills/webnote-workflow/steps/)**，改流程改那里，本文随之更新。

把"内容采集 → 提炼笔记 → 核查 → 确认发布"拆成**调度器（主会话） + 两个独立 Agent** 分工协作。分类不在这里定：类目归用户，`steps/03-confirm.md` 按用户自己的体系给去向。

不是每一步都需要独立的 AI 上下文。确定性的事调度器（主会话）自己干，只有真正需要独立判断的才交给 subagent。

## 架构总览

```
调度器（主会话）
├── 1. 采编（主会话自己做——确定性逻辑）
│      读 skills/webnote-workflow/steps/00-collect.md，按媒体类型路由，只加载命中的分支卡
│      → 产出 00-采编清单.md
│
├── 2. 创建 subagent：笔记匠 ← 独立上下文
│      读 skills/webnote-workflow/steps/01-distil.md
│      每条要点标注出处与来源类型
│      → 产出 01-笔记.md
│
├── 3. 创建 subagent：核查官 ← 全新上下文，必须独立
│      读 skills/webnote-workflow/steps/02-verify.md
│      逐条比对，三态判定
│      → 产出 02-核查表.md
│
└── 4. 确认（主会话自己做——汇总+约束）
       读 skills/webnote-workflow/steps/03-confirm.md
       按用户自己的分类体系给去向
       → 产出 03-待确认提案.md（全部停在"待确认"）
```

**为什么有些步骤不是独立 Agent：**

| 步骤 | 是否独立 | 理由 |
|------|---------|------|
| 采编 | ❌ 主会话内化 | URL 分类用规则，文本提取调用 CLI 工具——都是确定性逻辑，不需要 AI。AI 做反而可能猜错 |
| 笔记匠 | ✅ 独立 | 提炼是核心创作任务，需要完整上下文专注正文 |
| 核查官 | ✅ **必须独立** | 这是安全闸门。笔记匠自己核查自己等于自检——它查不出自己刚才编了什么 |
| 确认 | ❌ 主会话内化 | 不读原文、不重新核查，只是汇总前两份产出 + 按用户的分类体系给去向 + 约束落地行为 |

---

## 四步索引

**流水线的唯一定义在 [`skills/webnote-workflow/steps/`](../skills/webnote-workflow/steps/)：文件名即顺序。**

| 文件 | 产物 | 执行者 | 上下文 |
|---|---|---|---|
| [00-collect.md](../skills/webnote-workflow/steps/00-collect.md) | `00-采编清单.md` | 调度器 | 主会话 |
| [01-distil.md](../skills/webnote-workflow/steps/01-distil.md) | `01-笔记.md` | subagent | `isolated` |
| [02-verify.md](../skills/webnote-workflow/steps/02-verify.md) | `02-核查表.md` | subagent | `fresh`（必须） |
| [03-confirm.md](../skills/webnote-workflow/steps/03-confirm.md) | `03-待确认提案.md` | 调度器 | 主会话 |

每个步骤文件头部带 frontmatter：`step` / `context` / `reads` / `writes` / `forbidden` / `produces` / `format_needles`。最后一项是产出格式的**定义处**——`runs/_template/` 与它逐条比对，测试会拦。

这张表是给人看的导航，**不是第二份定义**：加一步就是加一个 `05-*.md`，表和测试都读目录，不需要再改别处。派发规则见 [skills/webnote-workflow/SKILL.md](../skills/webnote-workflow/SKILL.md)。

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

判据与真实案例见 [steps/02-verify.md](../skills/webnote-workflow/steps/02-verify.md)。

---

## 三条不可逾越

**本节是三条铁律的唯一定义处。** 其他文件（`AGENTS.md`、`SKILL.md`、记忆）只写指针，不重写——过去两处各写一版，结果第三条一处是「不改写用户已有文件」、一处是「落地必待确认」，调度器与入口对"闸门是什么"答得不一样。

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

> **注意**：`skills/webnote-workflow/SKILL.md` 是总路由卡；`skills/web-archive/SKILL.md` 承载防复制页、云文档和懒加载长文的无损拓存分支。流水线定义（`skills/webnote-workflow/steps/`，五个步骤文件 + `branches/`）与工具（`tools/`）是流程资产，归项目根。SKILL.md 第一步会先定位项目根（判定标准是目录下同时存在 `docs/architecture.md` 和 `tools/`），所以**完整流程必须在项目根工作区内运行**。角色不需要注册：`steps/0N-*.md` 是平台无关的定义文件，把文件路径交给子 agent 即可；工具若不支持 subagent，走方式二。

### 方式二：一条提示词（不装配也能用）

把 [`AGENTS.md`](../AGENTS.md) 与内容一起交给 AI——它本身就是入口说明，含步骤清单、可写范围与执行规则。

没有 subagent 能力的聊天界面，改用模式 B 的三段式提示词：[`mode-b-single-dialog.md`](../skills/webnote-workflow/mode-b-single-dialog.md)。

### 方式三：手动文件流水线

按四步顺序，每次让 AI 读对应的定义文件。采编和确认由你手动串起来。

每次运行在 `runs/` 下建子目录 `YYYY-MM-DD-主题`，五个输出文件并列写入。原文不复制、不移动，仅记录来源路径。多次运行互不覆盖。

完整格式契约见 [`runs/_template/`](../runs/_template/)；两态核查时代的历史产物见 [`docs/history/`](history/2026-09-03-two-state-example/)。

---

## 为什么是这套结构

三道切分不是从方法论推出来的，每一条都对应一类具体失败——去掉它，对应的失败就会回来：

| 切分 | 挡住的失败 | 判据 |
|---|---|---|
| 采编 / 确认留在主会话，只有笔记匠与核查官独立 | 已读过正文之后再起一个新上下文去打一个标签，只是把同一份材料重读一遍，而标签没有任何下游消费者 | 这一步要不要**独立的判断**，以及**错了的代价** |
| 核查官与笔记匠零共享上下文 | 写的人给自己打分必然通过——同一份上下文里"我写错了"和"我的判断错了"是同一个判断 | 自证不算核查 |
| 提炼必须标来源类型（原文 / OCR / ASR / Vision） | 二手转述被当成已验证事实写进知识库，且事后无法区分 | 一眼能看出这条是"读到的"还是"转述来的" |
| 落地动作（删 / 发布 / 改记忆）停在确认前 | 这三类撤不回来 | 这个动作错了，撤得回来吗 |

代价也是真的：多一次上下文切换、多一份格式约束、每轮多一道人工确认。愿意付，是因为一次编造混进知识库的修复成本远高于这三样。

## 一句话纪律

**AI 可以无限地"想"和"建议"，但凡要"落地动手"，停在你这道闸前。**

---

> 工具依赖：BrowserSkill（`bsk` CLI，只在正文为空 / 需渲染时调用）。说明副本在 [`skills/browser-skill/`](../skills/browser-skill/SKILL.md)（从上游直取，`python tools/check_vendor.py --pull` 升版，勿手改），命令以 `bsk --help` 为准。
