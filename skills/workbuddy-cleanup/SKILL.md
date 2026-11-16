---
name: workbuddy-cleanup
display_name: WorkBuddy 工作空间体检与到期回收
display_name_en: WorkBuddy Workspace Health & Retention Cleanup
description: WorkBuddy 自身工作空间的体检 + 到期自动回收技能（v9.3）。当用户说「工作空间体检」「清缓存」「定时清理」「清理缓存」「查占用地图」「工作空间占用」「哪些空间可以清」「清已删空间」「隔离区到期释放」「到期回滚/备份清理」「保留回滚」「改期限」「取消保留」时使用。只自动动四类：白名单缓存、到期隔离批次、到期回滚/备份、严格筛选的已删空间（同盘移隔离区）；其余一律只出清单等口令。红线：绝不删活空间、会话正文、projects、数据库、命名文件、回收站。区别于 c-drive-cleaner（整机 C 盘清理），本技能只管 .workbuddy 内部。
description_zh: WorkBuddy 自身工作空间的体检 + 到期自动回收技能（v9.3）。四类自动动作：清白名单缓存、释放到期隔离批次、清到期回滚/备份、把严格筛选的已删空间同盘移入隔离区。其余只出清单等口令。绝不删会话正文、活空间、数据库、命名文件。
description_en: WorkBuddy workspace health check and retention-based cleanup (v9.3). Four automatic actions only: whitelisted caches, expired quarantine batches, expired rollback/backup files, and same-drive quarantine of strictly filtered deleted spaces. Everything else is report-only until an explicit command. Never touches session bodies, live spaces, the DB, or display-name files.
version: 1.0.0
author: Joshuataokun
tags: WorkBuddy,工作空间,清理,缓存,体检,占用地图,隔离区,回滚,备份,清已删空间,保留回滚,改期限,v9.3
---

# WorkBuddy 工作空间体检与到期回收（v9.3）

## 中文速览

这是 WorkBuddy **自身**的体检与回收技能，不是整机 C 盘清理（那是 `c-drive-cleaner`）。它只管 `C:\Users\Administrator\.workbuddy` 内部和 `E:\WorkBuddy` 下的空间目录。核心思路：**默认只读出清单，只有四类到期/白名单对象自动处理，其余等用户一句口令**。铁律是「宁可一个字节都不删，也不许越界；漏清是小事，误删不可逆」。

## 一、什么时候用

用户说这些话时触发：工作空间体检 / 清缓存 / 定时清理 / 清理日志 / 查占用地图 / 哪些空间能清 / 清已删空间 / 隔离区到期 / 到期回滚 / 保留回滚 / 改期限 / 取消保留。

用户问整机磁盘、C 盘满了、哪个软件占空间 → 走 `c-drive-cleaner`，不走本技能。

## 二、自动动作只有四类（其余全部只出清单）

| 类 | 动作 | 授权来源 | 期限从哪读 |
|---|---|---|---|
| 2 缓存 | 白名单目录逐文件删，24h 内不动 | 策略 `autoDeleteWhitelist` | 各规则 `ttlHours` |
| 2.5 隔离区 | 到期批次释放（删到批次根） | 用户 11-04「自动检测超期隔离，自动删」 | `quarantine.ttlDays` |
| 2.6 回滚备份 | 三类到期条目删（仅三个具名子目录） | 用户 11-09「所有回滚备份设期限」 | `retention.classes[].ttlDays` |
| 2.7 已删空间 | 严格筛选后**同盘移入隔离区**，不直接删 | 用户 11-09「按方案 C 执行」 | `spaceQuarantine.ttlDays` |

**红线（一个字节都不许动）**：会话（含已删）、对话正文 `*.jsonl`、`projects\`、`workbuddy.db`、`workspace-display-names.json` 原件、附件/上传图、活空间任何文件、有活会话或有显示名的空间目录、隔离区未到期批次、回收站整体、`.workbuddy` 和 `E:\WorkBuddy` 整体递归扫描。

第 2 类例外边界：`workspace\sessions\` 整体是红线，只 `<sid>\` 下 `modify_backup` / `snapfile` / `.modify_backup_meta` 三个具名子目录可删，会话根目录本身不动。

## 三、执行前必读

1. **完整规格**：`references/spec-v9.3.md` —— 四类动作的判定、保护、报告格式、V1–V11 验收，动手前必须读。
2. **踩过的坑**：`references/pitfalls.md` —— 11-16 这轮新查出来的坑都在里面（并发锁、全局预算连坐、回收站假释放、大小写归一化、checkpoint 不等于完成等）。**这是本技能最重要的部分，动手前必读。**
3. **策略字段**：`references/policy.md` —— `cleanup-policy.json` 哪些字段是开关、哪些只是注释（注释不能当开关读）。
4. **脚本用法**：`scripts/README.md` —— 四阶段脚本的调用顺序与参数。

## 四、执行骨架（每一步都不能省）

```
启动锁 → 读策略 → 只读扫描 + 冻结四类计划 → 命名文件灾备(SHA256)
  → 逐阶段执行(单线程/独立预算/幂等) → 三段对账 → V1-V11 验收
  → 写运行记录 + 更新 cleanup-state.json → 删锁
```

### 1. 锁
`$WB\cleanup.lock = {"pid":<int>,"startedAt":<毫秒>,"host":"<主机名>"}`。有效锁且 pid 存活 → 跳过；僵尸锁可接管；**结束必须删锁（try/finally）**。本轮就因中途被用户打断、未走 finalize，锁一直留在盘上。

### 2. 策略唯一源
`$WB\cleanup-policy.json`。读不到或损坏才用内置默认并报告。**期限数字一律读策略，不许写死**；`note` / `authorizedBy` / `*Note` / `firstRun` 是注释，不作开关。

### 3. 扫描与执行分离（计划冻结）
先扫后删。**执行阶段只按 `<ts>` 冻结的四份计划文件操作，绝不重新枚举目录决定删什么**。四类各一份：`plan-<ts>.json` / `release-<ts>.json` / `retention-<ts>.json` / `spaces-<ts>.json`，放 `$WB\cleanup-runs\`。删前逐条重取 `size` / `mtime`，不一致 → `skipped_changed`。

### 4. 分阶段执行（11-16 新增，见坑 #1 #2）
**一次调用只跑一个 phase，各阶段独立预算、独立结果文件**。绝不能一个脚本串跑四类共用一个总预算——隔离区释放耗光预算后会把后面的回滚/空间阶段一起跳过，连续多轮卡死在同一处。

- 每轮从头扫全量冻结清单，已删项 `verify_item` 判 `not_found` 直接跳过（幂等）。
- 逐文件删、`WORKERS=1` 单线程；并发会触发 safe-delete 全局锁竞争被杀进程。
- 每 CHUNK 落盘进度；完成判据是**全量回读 remain=0 + 批次目录 Test-Path=False**，不是看 checkpoint 文件。

### 5. 三段对账
删完同时量**目标目录 / 可用空间 / 回收站**。safe-delete 把实体搬进回收站，目录清零但可用空间几乎不变 → 报告写「已移出，实体进回收站，需你手动清空才真正释放」，**不许写「已释放 X MB」**。回收站整体是红线，绝不自动清空（除非用户明确要求）。

### 6. 报告
Markdown 48 行内，占用地图按体积降序每行写「性质」（是什么、删了怎样、按什么期限清）；验收压一行 `V1✓ … V11✓`；结尾写回收站占用。**报告只输出在对话里，不往工作空间写报告文件**。

## 五、口令协议

报告末尾列可用口令，用户下一句说了才执行，本次一律不动（四类自动动作除外）：

`清缓存` / `清已删空间` / `保留回滚 <id前8位>` / `取消保留 <id前8位>` / `改期限 <类目> <天数>` / `清已删会话残骸` / `清无引用上传图` / `清索引残留` / `清 tool-results` / `恢复 <批次>`。

已移除 `清回滚备份`（改自动）；没有「释放隔离区」口令（自动）。执行任何口令：先列清单 → 一律先进隔离区（同盘 Move，失败不回退成直接删）→ 执行前重算归属 → 逐文件删 + 三步删空目录 → 给删前/删后/差值。

## 六、环境前提与性能（11-16 查证，写进报告）

平台默认开启「删除保护」（删除优先移回收站）+「批量删除审批」（默认 50 个一审批），这是删除慢、可用空间不涨、消耗积分和时间的根因。官方设置路径：

- `设置 → 安全中心 → 数据安全`：关「删除保护」（关后按系统删除，不再进回收站）、关「批量删除审批」（依赖删除保护）。
- `设置 → 安全中心 → 沙箱安全 → 文件安全`：把清理路径的删除从「询问」改「允许」。
- 输入框底部「默认权限」→「允许完全访问」：**全局开关、不跨设备、用完即关**。

⚠️ 关掉删除保护＝永久删除不可恢复，与「误删不可逆」铁律冲突。建议只对隔离目录短时开启，别全局长期开。

**不调到这些设置也能跑**，但要按实测吞吐规划：safe-delete 约 0.18 秒/文件（5.4 文件/秒），3 万文件约 100 分钟。必须分轮幂等续跑，不要试图一轮跑完；也不要用后台任务（后台删除会触发批量确认拦截）。

## 七、关键坑速查（完整见 references/pitfalls.md）

1. 并发删除触发 safe-delete 全局锁 `EPERM mkdir .lock` → 单线程。
2. 一个脚本串跑四类共用一个总预算 → 阶段连坐跳过 → 分阶段独立预算。
3. 删除进回收站，目录清零但可用空间不变 → 三段对账，不许报「已释放」。
4. checkpoint 写了 `done` 不代表真完成（实测 `release_done 1/1` 但还剩 12097 项）→ 完成只看全量回读。
5. Windows 路径大小写（`Claw` vs 归一化 `claw`）→ 活会话误判为 0 → 所有路径 `normcase` 后比较。
6. 扫描断言 `all()`/`any()` 写反 → retention 少算 → 改完必须重跑扫描重新冻结计划。
7. 空间移走后应用按旧路径重建同名空壳 → 不二次移动，只报告。
8. safe-delete 删成功也抛错 / 后台任务触发 `CONFIRM_REQUIRED` → 成功只认 `Test-Path`；删除不放后台。
9. `tasklist` 默认 UTF-8 解 GBK 输出崩 → `capture_output` + `decode('gbk')`。
10. PowerShell 5.1 不支持 `&&` → 用 `;`。

## 八、当前磁盘残留状态（2026-11-16，交接用）

定时任务已由用户删除，留了半截现场。**数字会随回读变化，不要照抄，重跑前先用 `status.py` 量一次**：

```
WB_CLEAN_WORKDIR="C:/Users/Administrator/AppData/Local/Temp/wbv93" python scripts/status.py
```

移交时（15:10 回读）大致状态：`C:\...\cleanup-quarantine\20261104` 批次还剩约 8300 个碎文件（<1 MB）、retention 14546 项中约 895 项已删（是被打断的第二轮干的，未落盘）、4 个空间已移入 `E:\WorkBuddy\.trash-quarantine\20261116`（manifest 合法，到期 2026-11-23）、僵尸锁 `cleanup.lock` 仍在（pid 14464 已死）。

后续若重跑：先删僵尸锁 → 用同一 `WB_CLEAN_WORKDIR` 指向旧现场 → 按冻结计划分阶段续跑（`finish.py release` / `retention` / `spaces` / `finalize`）。**不要重新扫描覆盖旧计划**，除非确认计划本身有错（见 pitfalls A5/A6）。

---

**版本**：1.0.0（2026-11-16）。由定时任务 v9.3 规格转化，新增「分阶段独立预算」「平台安全限制与性能」两节，并把 11-16 实测的 10 条坑写入 `references/pitfalls.md`。
