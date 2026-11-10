---
name: workspace-converge
display_name: 空间收敛
display_name_en: Workspace Converge
description: 空间治理与收尾清理。收尾时刻由 Stop hook 自动按白名单清理本轮新建的中间产物（首次 dry-run 出清单、之后自动删并留台账，交付物、大文件、被引用一律不删）；用户说「收敛 <空间名>」「压缩记忆」「精简脚本」「任务收敛」时做 B 档（快照+md5→清单待确认→压 MEMORY≤3000＋五项核验→旧日志移 archive→草稿脚本移 _archive→坑体检→收敛记录）。含防误删、防记忆污染、防路径失效、止损三条款；归档隔离单元带 3 天 TTL，再次运行收敛时自动释放已过期的垃圾类文件（记忆快照与交付物永不自动删）。另在阶段边界说「交接」时生成 HANDOVER 会话态快照，压缩后由 SessionStart 注入摘要接上进度。不适用于纯问答、讲概念、只读分析。当用户提到 收敛、收尾、压缩空间记忆、精简脚本和产物、空间整理、清理中间产物、止损、到期清理、TTL、交接、存档、上下文压缩 时使用。
description_zh: 空间治理与收尾清理。Stop hook 自动按白名单清本轮中间产物（首次 dry-run 出清单、之后自动删并留台账）；用户说「收敛 <空间名>」「压缩记忆」「精简脚本」时做 B 档（快照+md5→清单待确认→压 MEMORY≤3000＋五项核验→旧日志移 archive→草稿脚本移 _archive→收敛记录）。含防误删、防记忆污染、止损三条款；归档带 3 天 TTL。不适用于纯问答、讲概念、只读分析。当用户提到 收敛、收尾、压缩空间记忆、精简脚本和产物、空间整理、清理中间产物、止损、到期清理、TTL、交接、上下文压缩 时使用。
description_en: Workspace governance and end-of-turn cleanup. A Stop hook automatically removes this turn's intermediate artifacts from a narrow allowlist - first run is a dry-run checklist, later runs delete with sha256 backup and ledger, and deliverables, large or referenced files are always pinned. Tier B runs on converge / compress memory / trim scripts - snapshot with md5 verification, checklist for approval, compress MEMORY.md under 3000 chars with five-way verification, archive old logs and draft scripts, write a convergence record. Guardrails against wrongful deletion, memory contamination, stale paths, and repeated failed attempts. Quarantine units carry a 3-day TTL. HANDOVER snapshots keep in-flight state across compaction. Not for pure Q&A, concept explanations, or read-only analysis. Use when the user mentions converge, wrap up, compress space memory, trim scripts, clean intermediate artifacts, stop-loss, expiry cleanup, TTL, handoff, or context compaction.
version: 1.8.0
author: Joshuataokun
tags: 收敛,收尾,压缩记忆,精简脚本,空间整理,记忆维护,令牌比对,防误删,防污染
---

# 空间收敛（两档）

## 中文速览

```
A 档·收尾（同一个 Stop 时刻）：守卫补卡 → 归属表定唯一落点 → 清理脚本按白名单清本轮中间产物（首次 dry-run）→ 有产出才追加日志
B 档·空间收敛（用户说「收敛」）：先量+到期清理 → 快照+md5 → 清单待确认 → 压记忆（原子写）
        → converge.py verify 五项 → 蒸日志（带索引）→ 清草稿脚本 → 搬家后复验 → 报告
```

交接（阶段边界，用户说「交接」）：写 HANDOVER → 用户决定何时压缩 → 压缩后/新会话由 SessionStart 注入摘要接上

铁律三句：**候选区可以脏，正式记忆必须干净；拿不准就保留；验钥匙的清单要跑脚本，不许凭记忆列。**

## 何时不要用

- **纯问答、讲概念、只读分析**——不记结论、不落日志（A 档只服务于有产出的任务）
- **记忆未超 3,000 字符、日志未超 10 份**——不做 B 档，最多说一句"现在不需要"
- **任务做到一半**——判断不准且打断成本高，等交完再做
- **用户没指明空间名**——先反问，不许猜

## 收尾链与唯一归属（v1.7.0）

两个技能**不合并**：`my-project-card` 管项目状态板，`workspace-converge` 管空间资产治理。收尾统一到同一个 `hooks.Stop` 时刻，两个脚本并列、互不耦合。

**归属表主本**：`references/wrap-routing.md`（一张表定死什么写哪、收尾链顺序、删除硬规矩）。一张卡只写一处，别处最多留指针；卡片技能与本技能都只读这一份，改规则只改主本。

## A 档 · 任务收尾

1. 记结论：**只有换个会话推不出来的长期口径**才追加进 `.workbuddy/memory/MEMORY.md`；项目状态、进度、本轮做完的事写进项目卡。归属见 `references/wrap-routing.md`，**同一件事不许写两处**。
   写前先量：会超 3,000 只做「腾位级」微压（合并同类、删已失效行），**不整篇重写**——整篇属 B 档
2. 记坑：症状 → 根因 → 正确做法 → **触发场景**（什么情况下该想起它）→ 能不能写成代码里的判断。写前先查用户级记忆有无同条，有就只写本空间表现。**引用外部事实必须注明来源＋时点，并标一手/二手**（官方仓库、API 实测＝一手；博客、转述＝二手，须复核）；没来源标「待核实」
   **坑晋升**：复发≥2 或跨空间适用的坑，同步写进**本技能** `references/pitfalls-INDEX.md`（格式照文件头注释；已在用户级记忆里的不重复进）——那是 SessionStart hook 每会话注入的数据源，进索引＝下个会话开工必见
3. **止损回填**：本轮若发生过止损（见下），止损原因当场写成一条坑——止损不记坑＝同错再犯
4. 清本轮中间产物：**由 Stop hook 的 `wrap_cleanup.py` 自动做，助手不自己删文件**。首次运行强制 dry-run 出清单（`<空间>/.workbuddy/archive/wrap-首次清单.md`），第二次起按白名单自动删。白名单＝`__pycache__` 等缓存目录内容、`*.pyc/*.pyo/*.tmp`、带 `tmp_/test_/parse_/diag_` 前缀的 json/html/xlsx/log/out；单轮 ≤10，删前备份并校验 sha256、写 `wrap-ledger.md`、幂等。
   交付物、>1MB、被引用、路径越界、个人目录、拿不准的一律 pin；**来历不明的不删**，留给 B 档。停用：建空文件 `~/.workbuddy/.wrap-cleanup-off`
5. 当天日志 `.workbuddy/memory/YYYY-MM-DD.md` 追加一条，只写结论不写过程
6. 不蒸旧日志、不动别的空间

## 止损三条款（干活时生效，不等收尾）

- **返工熔断**：同一做法第 2 次失败 → 停。汇报已试过什么、失败在哪，列 2–3 个备选等用户选。**禁止第 3 次硬试**——「换个说法没换事」的反复重写（重命名脚本、换个函数名再来）也算同一次失败的第 2 次
- **方向门**：预计改动多个文件、动系统配置、或不可逆动作（部署/发布/删数据）开工前，一句话方案等用户点头再动手
- **放弃判据**：大活开工先说清「什么算做成、什么算做不成、什么情况直接放弃汇报」；到放弃线就停，输出现状报告而不是沉默硬扛

## B 档 · 空间收敛

7. 先量：MEMORY 字符数、日志份数与合计字符、脚本数与可复用数、已有回滚点
8. 先快照：`python scripts/converge.py snapshot <目录或文件>`（**自带逐文件 md5 校验**，输出"不一致 0"才算成功）。手抄 copy 不校验＝没验过。路径写进报告
9. 出清单等用户确认，不许边查边改
10. 压记忆：
   - 只留「换个会话、光看代码推不出来」的内容；**最重要的放文件顶部**（超预算从尾部截断）
   - 只合并、**不新写**（压缩时产生的新结论就是新错源）；**年代久不是删除理由**，看是否失效
   - 删除优先级：过程叙述 > 已交付清单 > 过期快照 > 失效路径；**用户拍板的口径与否决记录基本不删**
   - **别处有副本的，删全文只留指针**（"细则见技能 X""过程见日志 Y"）
   - **原子写**：先写 `.tmp` 再 `os.replace()`；直接覆盖＝写到一半被打断就成残档
11. 五项核验，一条命令：`python scripts/converge.py verify 旧.md 新.md --max-chars 3000 --max-lines 70`
    令牌（数字/版本/提交号/路径/URL）· 推测标记不得减少 · 路径 exists · 字符 · 行数。
    **任一 FAIL 即回滚**；确属故意更新的用 `--allow` 豁免并在报告写理由。
    路径项会展开 `~` 与 `%VAR%`；含 `<`（占位符）、`*`、`…` 或 `://` 的候选不计入（v1.4.1）。
12. 蒸日志：要点写回 MEMORY 或单独索引；原文件移 `archive/memory-日期/`，**不许删**；**必须建 `归档索引.md`**（不建索引＝把东西藏起来）。当天日志、含未决事项的日志不动
13. 清脚本，**两层判据缺一不可**：
    - 技术层：盘符在模块级常量（改一行可复用）→ 可留；散在函数逻辑里 → 归档。用 AST 判断，别用朴素正则（`http://` 的 `//` 会被误判）
    - 业务层：产物还活着吗（产物已删/已被取代 → 归档，哪怕技术上一行能改）
    - 归档前查两处引用：各空间 MEMORY.md、自动化 prompt——有引用先改引用
14. **搬家后复验**：11、13 步移了文件，重跑 verify ＋路径 exists，重点看指向被移动文件的引用
15. **坑体检**：扫本空间 MEMORY.md 的坑条目，逐条三选一——复发≥2 或跨空间 → 列出来建议晋升 `references/pitfalls-INDEX.md`（写操作，等用户点头）；仅本空间有效 → 留原地；已失效 → 标失效不删。同时反查索引：pitfalls-INDEX.md 里的坑还成立吗
16. 删「已排除方案/否决记录」时，**否决原因必须跟着保留**（写进收敛记录）——只删结论不删原因，下次同样条件会再想一遍
17. 暂存类目录（`_cleared-*`、`publish-*`）删除前，逐个子目录说明里面装的是什么原件，确认后再删

## 通用规则

18. 拿不准是否过期，一律保留并标「待确认」；宁可留错，不许删对
19. 两条记忆矛盾，不自己选边，列出来给用户裁决
20. 只碰当前空间；动别的空间或用户级记忆先问；该上移用户级的条目列出来问，上移前先量字符
21. 没快照不许删任何东西
22. 收敛记录写在**快照目录**里（`收敛记录-日期.md`）：删了什么、为什么、可从哪份快照恢复，**加三个数：耗时 / 字符前后 / 处置条数**。审计账不写进 MEMORY.md
23. 一页报告：改了什么（字符/文件数前后）、哪些没动及原因、矛盾待裁决、回滚点、**豁免令牌及理由**；没实测数字写「未验证」
    **压记忆必须附「处置表」**：只列删除与合并项，一条一行三列（原文摘要 / 处置 / 理由）。只保证"一条没丢"却不给对照＝用户无法核
24. 压缩不宜频繁：MEMORY 每次重写都会使平台缓存失效、下一次变贵变慢——**攒够触发条件再做**

## TTL 到期清理（v1.6.0，细则见 `references/ttl-guide.md`）

25. **归档即登记**：移入隔离单元当刻跑 `ttl.py init <目录>` 写 `_TTL.json`（归档/到期时间＋每文件 sha256）。**不靠 mtime**
26. **3 天到期**，不建定时任务；只在再次运行收敛时检查，只扫当前空间
27. **只删垃圾类**：草稿/诊断/测试/中间产物可删；记忆快照、旧日志、技能备份、交付物、基线/构建产物、仓库资产、>1MB 文件一律 **pin**。拿不准就 pin
28. **删前四闸**：manifest 合法 · 已过期 · 24h 无写入 · 未被引用（purge 前刷新 `ttl-refs.txt`）。通用文件名不凭同名拦
29. **首次强制 dry-run**，第二次起才真删；两阶段（冻结清单→按清单删＋删前复核）、路径断言、写 ledger、回读、幂等
30. **台账不是恢复源**，删除不可逆；3 天窗口内说「保留 <文件>」→ `ttl.py pin <目录> --file <路径>`

## 上下文交接（v1.8.0，细则见 `references/handoff-guide.md`）

31. **压缩不要求换会话**：平台自动压缩后仍在同一任务里；丢的是中间推理、已读文件内容、多步状态、口头偏好和「下一步」。解法是压缩前把会话态落到文件，**不是一句话一个会话**
32. **HANDOVER 只写卡片里没有的东西**：`<空间>/.workbuddy/HANDOVER.md` 六个固定小节——目标 / 已定口径与结论 / 改过的文件 / 踩过的坑 / 未决问题 / 下一步。后三类之外的结论**只留指针**（见卡片 / MEMORY / 当天日志），不复制内容（收尾归属表：一事实只写一处）
33. **触发与收口**：用户说「交接」「存档」→ 我写好六项内容，跑 `handoff.py save --space <空间> --content <文件>`（字段校验＋原子写＋更新全局活跃指针），回一句「现在可以压缩了」。**平台压缩由用户决定，我不触发**。任务真正完成说「收交接」→ `handoff.py clear` 归档文档、撤销指针（不删除）
34. **压缩后怎么接上**：SessionStart 的 `pitfall_inject.py` 顺带注入 HANDOVER 极简摘要（≤220 字符：目标 / 下一步 / 未决数 / 全文路径）；要读全文说「读交接」→ `handoff.py show`。活跃指针只保留最近一份，7 天过期自动不注入。**复用现有 hook，不新增常驻钩子、不碰平台配置**
35. **时机按阶段边界判，不凭感觉**：研究→方案 / 方案→实施 / 失败换方向 / 里程碑→新工作 适合交接；**实施中途不适合**（变量名、路径、半成品丢了代价高）。完整判据表、什么能存活于压缩、调研出处见 `references/handoff-guide.md`；大工具输出落文件只留指针，从源头少占上下文

## 脚本

| 脚本 | 用途 |
|---|---|
| `scripts/converge.py verify 旧 新` | 五项核验一条命令，退出码 1 = 有 FAIL，即回滚 |
| `scripts/converge.py snapshot <路径>` | 快照＋逐文件 md5 校验（回滚点） |
| `scripts/tokens.py extract/check` | 单看令牌与推测标记（verify 已含） |
| `scripts/ttl.py init/backfill/scan/purge/pin` | 隔离区 3 天到期清理，**命令格式见 ttl-guide.md** |
| `scripts/wrap_cleanup.py` | Stop hook 调用：本轮中间产物只读扫描 → 首次 dry-run → 之后按白名单删（备份+sha256+台账） |
| `scripts/acceptance_wrap.py` | 上一条的 22 项回归（临时 HOME 里跑，绝不碰真实环境），**改清理规则必跑** |
| `scripts/handoff.py save/show/clear/summary` | 交接文档写入 / 读全文 / 归档撤销 / 注入摘要 |
| `scripts/pitfall_inject.py` | SessionStart 注入：8 条坑 ＋ 活跃 HANDOVER 摘要（不新增 hook 条目） |

只依赖标准库。别用肉眼代替——2026-10-29 实测：手工列的 32 个令牌号称零丢失，脚本一跑漏 3 个指针。

## 参考

- `references/wrap-routing.md`：**收尾归属表主本**（唯一落点 / 收尾链 / 删除硬规矩），改规则先读
- `references/templates.md`：处置表 / 归档索引 / 收敛记录 / 快照 的照抄模板
- `references/ttl-guide.md`：TTL 全部细则、命令速查、与每周体检 v9.3 的分工（**改 TTL 规则前先读**）
- `references/handoff-guide.md`：交接细则、阶段边界表、调研出处（**改交接规则前先读**）
- `references/changelog.md`：版本变更与全部由来（**改规则前先读**）
- `evals/scenarios.md`：八个验收场景（正常 / 输入不全 / 误用边界 / 误删防护 / 止损 / TTL / 收尾清理 / 交接），**改完必跑**
