---
name: workspace-converge
display_name: 空间收敛
display_name_en: Workspace Converge
description: 任务收尾与空间收敛。任务有产出交完时做 A 档（记结论、记坑、清本轮中间产物）；用户说「收敛 <空间名>」「压缩记忆」「精简脚本」「任务收敛」时做 B 档（快照+md5→清单待确认→压 MEMORY≤3000＋五项核验→旧日志移 archive→草稿脚本移 _archive→收敛记录）。含防误删、防记忆污染、防路径失效、防"猜测被写成定论"的规定。不适用于纯问答、讲概念、只读分析。当用户提到 收敛、收尾、压缩空间记忆、精简脚本和产物、空间整理、清理中间产物 时使用。
description_zh: 任务收尾与空间收敛。任务有产出交完时做 A 档（记结论、记坑、清本轮中间产物）；用户说「收敛 <空间名>」「压缩记忆」「精简脚本」「任务收敛」时做 B 档（快照+md5→清单待确认→压 MEMORY≤3000＋五项核验→旧日志移 archive→草稿脚本移 _archive→收敛记录）。含防误删、防记忆污染、防路径失效、防"猜测被写成定论"的规定。不适用于纯问答、讲概念、只读分析。当用户提到 收敛、收尾、压缩空间记忆、精简脚本和产物、空间整理、清理中间产物 时使用。
description_en: Task wrap-up and workspace convergence. Tier A runs after a task that produced artifacts (record conclusions, pitfalls, clean this round's intermediates). Tier B runs on "converge <workspace>" / "compress memory" / "trim scripts": snapshot with md5 verification, checklist for approval, compress MEMORY.md under 3000 chars with five-way verification, archive old logs and draft scripts, write a convergence record. Not for pure Q&A, concept explanations, or read-only analysis. Guardrails against wrongful deletion, memory contamination, stale paths, and hedged guesses hardening into facts.
version: 1.4.0
author: Joshuataokun
tags: 收敛,收尾,压缩记忆,精简脚本,空间整理,记忆维护,令牌比对,防误删,防污染
---

# 空间收敛（两档）

## 中文速览

```
A 档·任务收尾（有产出时自动）：记结论 → 记坑 → 只清本轮新建的中间产物 → 当天日志追加
B 档·空间收敛（用户说「收敛」）：先量 → 快照+md5 → 清单待确认 → 压记忆（原子写）
        → converge.py verify 五项 → 蒸日志（带索引）→ 清草稿脚本 → 搬家后复验 → 报告
```

铁律三句：**候选区可以脏，正式记忆必须干净；拿不准就保留；验钥匙的清单要跑脚本，不许凭记忆列。**

## 何时不要用

- **纯问答、讲概念、只读分析**——不记结论、不落日志（A 档只服务于有产出的任务）
- **记忆未超 3,000 字符、日志未超 10 份**——不做 B 档，最多说一句"现在不需要"
- **任务做到一半**——判断不准且打断成本高，等交完再做
- **用户没指明空间名**——先反问，不许猜

## A 档 · 任务收尾

1. 记结论：本轮定下的口径、路径、结论，追加进 `.workbuddy/memory/MEMORY.md`
   写前先量：会超 3,000 只做「腾位级」微压（合并同类、删已失效行），**不整篇重写**——整篇属 B 档
2. 记坑：症状 → 根因 → 正确做法 → 能不能写成代码里的判断。写前先查用户级记忆有无同条，有就只写本空间表现。**引用外部事实必须注明来源＋时点，并标一手/二手**（官方仓库、API 实测＝一手；博客、转述＝二手，须复核）；没来源标「待核实」
3. 清本轮中间产物：只删**本轮新建的**（解析 json、test_*.xlsx、`__pycache__`、临时 html），逐项列进报告
   交付物（xlsx/docx/成图）一个都不动；**来历不明的不删**，留给 B 档
4. 当天日志 `.workbuddy/memory/YYYY-MM-DD.md` 追加一条，只写结论不写过程
5. 不蒸旧日志、不动别的空间

## B 档 · 空间收敛

6. 先量：MEMORY 字符数、日志份数与合计字符、脚本数与可复用数、已有回滚点
7. 先快照：`python scripts/converge.py snapshot <目录或文件>`（**自带逐文件 md5 校验**，输出"不一致 0"才算成功）。手抄 copy 不校验＝没验过。路径写进报告
8. 出清单等用户确认，不许边查边改
9. 压记忆：
   - 只留「换个会话、光看代码推不出来」的内容；**最重要的放文件顶部**（超预算从尾部截断）
   - 只合并、**不新写**（压缩时产生的新结论就是新错源）；**年代久不是删除理由**，看是否失效
   - 删除优先级：过程叙述 > 已交付清单 > 过期快照 > 失效路径；**用户拍板的口径与否决记录基本不删**
   - **别处有副本的，删全文只留指针**（"细则见技能 X""过程见日志 Y"）
   - **原子写**：先写 `.tmp` 再 `os.replace()`；直接覆盖＝写到一半被打断就成残档
10. 五项核验，一条命令：`python scripts/converge.py verify 旧.md 新.md --max-chars 3000 --max-lines 70`
    令牌（数字/版本/提交号/路径/URL）· 推测标记不得减少 · 路径 exists · 字符 · 行数。
    **任一 FAIL 即回滚**；确属故意更新的用 `--allow` 豁免并在报告写理由
11. 蒸日志：要点写回 MEMORY 或单独索引；原文件移 `archive/memory-日期/`，**不许删**；**必须建 `归档索引.md`**（不建索引＝把东西藏起来）。当天日志、含未决事项的日志不动
12. 清脚本，**两层判据缺一不可**：
    - 技术层：盘符在模块级常量（改一行可复用）→ 可留；散在函数逻辑里 → 归档。用 AST 判断，别用朴素正则（`http://` 的 `//` 会被误判）
    - 业务层：产物还活着吗（产物已删/已被取代 → 归档，哪怕技术上一行能改）
    - 归档前查两处引用：各空间 MEMORY.md、自动化 prompt——有引用先改引用
13. **搬家后复验**：11、12 步移了文件，重跑 verify ＋路径 exists，重点看指向被移动文件的引用
14. 删「已排除方案/否决记录」时，**否决原因必须跟着保留**（写进收敛记录）——只删结论不删原因，下次同样条件会再想一遍
15. 暂存类目录（`_cleared-*`、`publish-*`）删除前，逐个子目录说明里面装的是什么原件，确认后再删

## 通用规则

16. 拿不准是否过期，一律保留并标「待确认」；宁可留错，不许删对
17. 两条记忆矛盾，不自己选边，列出来给用户裁决
18. 只碰当前空间；动别的空间或用户级记忆先问；该上移用户级的条目列出来问，上移前先量字符
19. 没快照不许删任何东西
20. 收敛记录写在**快照目录**里（`收敛记录-日期.md`）：删了什么、为什么、可从哪份快照恢复，**加三个数：耗时 / 字符前后 / 处置条数**。审计账不写进 MEMORY.md
21. 一页报告：改了什么（字符/文件数前后）、哪些没动及原因、矛盾待裁决、回滚点、**豁免令牌及理由**；没实测数字写「未验证」
    **压记忆必须附「处置表」**：只列删除与合并项，一条一行三列（原文摘要 / 处置 / 理由）。只保证"一条没丢"却不给对照＝用户无法核
22. 压缩不宜频繁：MEMORY 每次重写都会使平台缓存失效、下一次变贵变慢——**攒够触发条件再做**

## 脚本

| 脚本 | 用途 |
|---|---|
| `scripts/converge.py verify 旧 新` | 五项核验一条命令，退出码 1 = 有 FAIL，即回滚 |
| `scripts/converge.py snapshot <路径>` | 快照＋逐文件 md5 校验（回滚点） |
| `scripts/tokens.py extract/check` | 单看令牌与推测标记（verify 已含） |

只依赖标准库。别用肉眼代替——2026-10-29 实测：手工列的 32 个令牌号称零丢失，脚本一跑漏 3 个指针。

## 参考

- `references/templates.md`：处置表 / 归档索引 / 收敛记录 / 快照 的照抄模板
- `references/changelog.md`：版本变更与全部由来（**改规则前先读**）
- `evals/scenarios.md`：四个验收场景（正常 / 输入不全 / 误用边界 / 误删防护），**改完必跑**
