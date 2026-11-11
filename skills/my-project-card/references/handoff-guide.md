# 上下文交接 · 细则（v1.8.0）

> 正文 SKILL.md 第 31–35 条是精简版；本文件是权威细则。**改交接规则前先读这里。**

## 一、要解决的问题

复杂任务几轮对话就触发平台自动压缩，压缩时模型另起一轮生成摘要，会中断对话；压缩后**中间推理、已读文件内容、多步对话状态、口头偏好、下一步**会丢，接着做就变味。

用户 2026-11-10 口径：「总不能一句话一个会话吧？想主动掌握这个节奏」。

**先澄清一个误解**：自动压缩后仍在同一个会话里，不是必须开新会话。要解决的不是"换会话"，而是"压缩前后状态怎么接上"。

## 二、本机平台约束（实测，别照搬 Claude Code）

| 项 | 实测结果 |
|---|---|
| 压缩机制 | 有：`ContextSummaryAgent`、`<system-reminder data-role="compact-summary">` 摘要注入、会话级 runtime option **`preMessageCompactPct`**（与思考级别 / 上下文窗口并列） |
| **PreCompact 钩子** | **没有**（`app.asar` 里 `PreCompact` 出现 0 次）→ Claude Code 那套"压缩前自动抢救"照搬不了 |
| 可用 hooks | 只有 `SessionStart` / `Stop` / `SessionEnd`（已注册 2 / 3 / 1 条） |
| 压缩阈值配置 | `settings.json` 里没有任何 compact/threshold 键；官方文档未公开。能否在界面改 `preMessageCompactPct` **需用户手动确认**，本方案不碰 |
| 会话体量 | 最大 25.4 MB / 4739 行；单会话出现 22–38 次 compact 标记；81 个会话共 290.7 MB |

因此方案不碰平台配置、不新增 hook 条目，只**复用现有 SessionStart 注入通道**。

## 三、用户拍板（2026-11-10）

- 做**方案 A**：交接文档 + 阶段边界判据 + SessionStart 注入摘要
- HANDOVER 落点：**空间内** `<空间>/.workbuddy/HANDOVER.md`
- **不做** C（不调 `preMessageCompactPct`）、**不做** B（不加 Stop 水位 hook）、**不做** D（不只靠自觉）
- 不新建技能：跨会话状态与空间资产统一由卡片技能管（2026-11-11 收敛技能已卸载）

## 四、六字段模板（≤1500 字符）

```
## 目标
<一句话，这单要达成什么>

## 已定口径与结论
指针：见卡片 <slug> 主卡 / 空间 MEMORY.md（**不复制内容**）

## 改过的文件
指针：见当天日志 YYYY-MM-DD.md / git status

## 踩过的坑
指针：references/pitfalls-INDEX.md / 当天日志

## 未决问题
- <还没落卡、只在对话里口头说过的>
- 没有就写「无」

## 下一步
<一句话，压缩后第一件事做什么>
```

**为什么后三类之外只留指针**：`references/wrap-routing.md` 是收尾归属表唯一主本——项目状态、坑、进度唯一落在项目卡；MEMORY.md 只放长期口径；当天日志放过程。HANDOVER 再抄一遍就变成三份副本（2026-11-10 实测踩过）。**HANDOVER 独有的只有「目标 / 未决 / 下一步」这三样会话态**，恰好是压缩最先丢、卡片里没有的。

## 五、命令速查

```
S = ~/.workbuddy/skills/my-project-card/scripts/handoff.py

# 用户说「交接」「存档」→ 助手写好六项内容存成临时 md，再：
python $S save --space <空间根> --content <写好的.md>
# 校验六小节、≤1500 字符、原子写、更新全局活跃指针

python $S show            # 读当前活跃交接全文（用户说「读交接」）
python $S summary         # SessionStart 注入用极简摘要（≤220 字符）
python $S clear --space <空间根>   # 任务真正完成（「收交接」）：归档到
                                  # .workbuddy/archive/handoff-<时间>.md，撤销指针，**不删除**
```

**全局活跃指针** `~/.workbuddy/handoff-active.json`：只存最近一次交接的路径、空间、时间。7 天过期或目标文件消失 → 不再注入。只保留一份，避免多空间串味。换机后指针不进仓库，新机第一次说「交接」自动重建。

## 六、压缩后怎么接上

`scripts/pitfall_inject.py`（现有 SessionStart hook）在坑提醒后追加一段：

```
<handoff>
上次交接：<目标>
下一步：<下一步一句话>
未决：N 项｜全文 <空间>\.workbuddy\HANDOVER.md
</handoff>
```

≤220 字符，全文按需读（渐进披露）。**没有新增 hook 条目**，只是扩展现有脚本输出；import 失败静默，不影响坑提醒。

## 七、压缩 vs 重开 · 决策表（唯一主本，2026-11-11 用户拍板）

**结论**：主路线＝「交接 → **重开新会话** → 卡片 `resume` 续接」；压缩只作「同一子任务健康续跑」的次要路线。**不要往卡片技能里加"压缩上下文对话"能力**——压缩是平台行为（`ContextSummaryAgent` / `compact-summary` 注入），技能没有接口触发或改写它；`github/awesome-copilot` PR #5097 维护者一手原话：额外规则会与 harness 已有的 compaction / sub-agent / memory 流程**冲突或矛盾**。卡片技能只读这一节，别处最多留指针。

### 决策表

| 情况 | 走哪条 | 依据 |
|---|---|---|
| 同一子任务继续、会话健康、只是长文件读取/终端输出噪声多 | **让平台自动压缩**，压缩前说「交接」；不重开 | 重建上下文反而更贵；40–60% 或 15–25 轮适合 compact |
| 研究→方案、方案→实施、里程碑→新工作 | **重开**（方案已落文件） | 官方「SPEC.md 写好后开新会话，从干净上下文 + 书面完成定义开始」 |
| 同一件事纠正两次还不对、AI 忽略早期约束、对着旧版本改文件、工具参数频繁出错、响应变慢 | **立刻重开**，别再压缩 | 官方「`/clear` + 一条融入教训的新 prompt 几乎总是更好」；腐烂上下文会被压缩继承 |
| 任务跑到一半、上下文到顶、会话仍健康 | **压缩** | 官方给 `/compact` 的唯一保留场景 |
| 切换到无关任务 | **重开** | `/clear` between unrelated tasks，零成本 |

**「看到将满」不是好触发点**：外部口径一致「不要等硬上限」。上面那几个**退化症状**出现时往往还没满；等到平台提示时，模型可能已在用被污染的上下文工作。平台内部有 `context_usage` 运行时与 `tokenUsage / lastContextWindow` 记录，界面露出程度需用户确认。

### 重开后第一句标准动作（三步，顺序不能换）

1. `card.py resume` 读卡（简报「⚠ 开工先读」＋自动的「重开会话续接」提示）＋ 读 HANDOVER 全文；
2. **核对地面真相**：相关文件是否还在、`git status`、跑一遍验证命令。简报告诉你「当时站在哪」，实测才告诉你「现在实际如何」；
3. 再动手。新会话**必须选同一个工作区目录**，否则卡片与 HANDOVER 都对不上（最易翻车一步）。

### 与止损三条款对齐

卡片技能的「返工熔断」＝同一做法第 2 次失败即停、列备选等用户选。这里补上出口：**停下来的同时建议重开会话**，而不是继续压缩或硬试第 3 次。两者是同一条纪律的两端（止损 → 换干净上下文）。

### 阶段边界表（来自 GitHub `strategic-compact` 一手 SKILL.md）

| 阶段转换 | 交接/压缩？ | 理由 |
|---|---|---|
| 研究 → 方案 | ✓ | 调研素材 bulky，方案是蒸馏产物 |
| 方案 → 实施 | ✓ | 方案已落文件，腾空间给执行 |
| 实施 → 测试 | 看情况 | 测试要引用刚改的代码就别压 |
| **实施中途** | **✗** | 变量名、文件路径、半成品状态丢了代价高 |
| 失败方案 → 换方向 | ✓ | 先清掉死胡同推理 |
| 里程碑完成 → 新工作 | ✓ | 干净起点 |

**什么能存活于压缩**：规则文件 / 记忆文件 / 磁盘文件 / git 状态。
**什么会丢**：中间推理、之前读过的文件内容、多步对话上下文、工具调用历史、口头说过的偏好、`下一步`。官方原话：「对话里的话在压缩时会丢，重要的事要落到确定性机制」。该项目也警告：**别指望任务列表存活**——"把计划写进文件"是唯一可靠做法。

### 新增证据（2026-11-11，勿重复查）

- **Anthropic 官方 `code.claude.com/docs/en/best-practices.md`**（一手）：`/clear` between unrelated tasks costs nothing；「同一件事纠正两次仍不对，`/clear` + 融入教训的新 prompt 几乎总是更好」；「不需要历史时新会话仍更便宜」；`/compact` 本身是一次大请求；**「the sentence can get lost when the conversation compacts」**
- **Letta 官方 Recovery-Bench**（letta.com/blog，一手）：失败轨迹造成 context pollution；Terminal-Bench 平均 26.3% → Recovery-Bench **11.2%（相对 −57%）**；最强模型也会被失败历史分心
- **GitHub `github/awesome-copilot` PR #5097**（一手）：维护者拒绝额外 handoff 技能，理由是与 harness 内置 compaction / sub-agent / memory 流程冲突
- **GitHub `alapha888/session-handoff-kit` + Context Hygiene Checklist**：40–60% / 15–25 轮 → compact；>60–70% / >35 轮或退化症状 → fresh session；两分钟 pre-reset 流程
- **限定**：Anthropic 说「上下文已非主要瓶颈、激进管理过时」是 **1M 窗口**语境；本机实测单会话 22–38 次压缩标记、最大 25.4 MB / 4739 行，**不能照搬**

> 共同结论：主流不靠更频繁压缩，而靠「逻辑边界处换干净上下文 + 状态写进文件」。压缩只保留给「同一子任务健康续跑」。

## 八、调研出处（2026-11-10 与 11-11 两批，勿重复查；11-11 新增证据列在第七节末）

- **Claude Code**（SFEIR Institute 教程 / Tips）：自动压缩约 95% 触发；`CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=70` 可提前；`/compact` 手动且可带自定义指令；**PreCompact hook**（matcher `auto`/`manual`）压缩前把状态写成 HANDOVER；压缩前先写一条 recap 消息
- **OpenAI / Codex**（官方 "Unrolling the Codex agent loop" / "From model to agent"）：服务端原生 compaction（`/responses/compact`，`type=compaction` + `encrypted_content`）；`auto_compact_limit` 可配；**大工具输出落容器文件系统，消息里只留引用**
- **Gemini CLI**（Zread 源码解析）：`SNAPSHOT` / `ROLLING_SUMMARY` 节点带 `abstractsIds` 血缘链，**滞回触发**避免反复压缩
- **LangGraph / LangChain**：`SummarizationMiddleware` 支持 `trigger=("fraction", 0.8)`、`keep=("messages", 20)`；`summary_prompt` 可写死"保留所有数字、日期和人名"；Deep Agents 的 offloading
- **GitHub `affaan-m/everything-claude-code` → `skills/strategic-compact/SKILL.md`**（raw 一手读）：阶段边界决策表、what survives / what's lost、双信号提醒（真实 token 为主，工具调用数是**弱代理**）、"写计划到文件再压缩"

> 共同结论：**主流不靠"更频繁地压缩"，而靠"在逻辑边界压缩 + 压缩前把状态写进文件"**。平台没有 PreCompact 时，把"压缩点"交还给人、把"状态承接"交给文件，是同等效果的替代路径。

## 九、边界与已知局限

**2026-11-11 补充拍板**：主路线定为「交接 → 重开新会话 → 卡片 `resume` 续接」，压缩只保留给「同一子任务健康续跑」。卡片技能 2.1.2 起在简报与 `resume` 输出确定性提示续接三步；决策表主本就是本文第七节，两技能只留指针。


- **助手不触发平台压缩**，只写文档并说「现在可以压缩了」；压缩动作由用户决定（平台行为，技能无权调用）
- HANDOVER 是**会话级快照**，不是长期状态；任务完成要 `clear` 归档，否则 7 天后自动停止注入（文件仍在，不删）
- 全局指针只保留最近一份；同时在多个空间交接，只有最后一次会被注入（合理默认值）
- 注入摘要是极简的，细节必须 `show` 读全文；别指望摘要能替代全文
- 换机：脚本与本文随 `sync.sh` → GitHub → `restore.sh` 走；HANDOVER 与指针是空间数据，不进公开仓库，新机第一次说「交接」重建指针
- 未做（用户未选）：平台水位 `preMessageCompactPct` 调整、Stop 水位提醒 hook、用户级记忆触发词（余量不足 3,000 预算）
