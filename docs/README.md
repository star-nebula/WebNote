# 文档索引

| 文件 | 是什么 | 状态 |
|---|---|---|
| [architecture.md](architecture.md) | 当前架构：调度器 + 3 subagent、五步流水线、执行模式、目录约定 | **v3 · 现行** |
| [versions/v2-五个Agent到三个-2026-08-04.md](versions/v2-五个Agent到三个-2026-08-04.md) | 为什么把 5 个独立 Agent 精简成「调度器 + 3 subagent」（已发表） | v2 · 已被 v3 取代 |
| [versions/v1-四步工作流-2026-07-14.md](versions/v1-四步工作流-2026-07-14.md) | 四步工作流原版：整理 / 提炼 / 核查 / 确认（已发表） | v1 · 已被 v3 取代 |
| [decisions.md](decisions.md) | 决策记录（2026-10-31 从 SemanticMemory 迁入，持续追加） | 活文档 |

## 外部依赖

BrowserSkill 是本仓唯一的外部工具依赖，只在「图文但正文为空 / 需要渲染」时被 `tools/extract-webpage.py` 调用。

它有三个来源层级，别混：

| 层 | 位置 | 谁维护 |
|---|---|---|
| 真源 | [Tencent/BrowserSkill](https://github.com/Tencent/BrowserSkill) 的 `crates/bsk-cli/skill/` | 上游 |
| 技能库副本 | `browser-skill/`（本机技能库内） | 人工搬运，已落后于上游 |
| 本仓副本 | `skills/browser-skill/`（`SKILL.md` + `references/` 14 个文件） | 本仓，不改内容 |

真源与代际记在 `bot.yaml` 的 `vendored:` 段（上游地址 + 完整 commit + 快照日期）。`bsk` 可执行文件的版本号**不是**基准——别人机器上不一定有那个 exe。

检查：

```bash
python tools/check_vendor.py            # 离线：副本存在、是真目录、文件数、与 .skillshare 对齐（进 CI）
python tools/check_vendor.py --online   # 与上游逐个文件比 blob sha（需联网 / gh 登录）
```

刷新副本（仅在有技能库的机器上需要，两份同时覆盖，否则下次 sync 会退回旧版）：

```bash
# 1. 拉上游 crates/bsk-cli/skill/ 的 SKILL.md + references/
# 2. 同时覆盖 技能库的 browser-skill/ 与本仓 skills/browser-skill/
# 3. 跑 check_vendor.py --online 确认一致，更新 bot.yaml 的 ref / snapshot
```

`skillshare sync -p` 仍可用，但它只是把技能库那份镜像过来；技能库没更新时跑它等于回退。

## 三个版本的关系

同一套设计的三次收敛，不是一个产品的三个分支：

- **v1（2026-07-14）**：四步工作流。把整理、提炼、独立核查、人工确认拆成四个各管一段的 Agent，核心命题是"可信优先"——AI 编的东西要在落地前被拦下。
- **v2（2026-08-04）**：承认"不是每一步都需要独立 AI 上下文"。5 个 Agent 收敛成「调度器（主会话）+ 3 个 subagent」，只保留核查官必须全新上下文，其余确定性逻辑交回主会话。
- **v3（现行，代码与文档同源）**：采编与确认留在主会话；归类、提炼、核查三个步骤创建 subagent；流程细则落在 `skills/webnote-workflow/references/steps/`，角色定义在 `agents/`，工具在 `tools/`，验证在 `tests/`。改流程改 `architecture.md`，不改 v1 / v2 正文。

v1 / v2 是已发表文章的存档，**正文保持发表时原样**，只在开头加版本标记；其中的旧路径、旧目录名不必修正。
