# WorkBuddy 清理踩坑全集

> 分两段：**A. 2026-11-16 这轮新查出来的**（本次定时任务体检的产出，重点）；**B. 历史坑**（v7–v9.3 规格第 11 节已有，保留备查）。
> 每条按「现象 / 根因 / 证据 / 修复」写。修复落点指到脚本或规格章节。

---

## A. 2026-11-16 新查出来的坑

### A1. 并发删除触发 safe-delete 全局串行锁，进程被杀 ★高危

- **现象**：用 `ThreadPoolExecutor(max_workers=32)` 并发 `os.remove`，进程中途消失、无异常栈；stderr 出现 `[safe-delete][SAFE_DELETE_BULK_GUARD_ERROR] failed to acquire lock: EPERM: operation not permitted, mkdir 'C:\...\Temp\codebuddy-safe-delete-bulk\<hash>\.lock'`。
- **根因**：平台的 safe-delete 批量守卫是**全局串行锁**，并发删除抢同一 `.lock` 目录，`mkdir` 被拒直接杀进程。不是脚本逻辑问题，也不是阈值问题（前台单轮 200 个探针成功过）。
- **证据**：并发版 `bench2/bench3` 测速 `SPEEDUP=2.79x` 看似可用，但真正批量执行时崩；改单线程后连删 3217 文件零报错。
- **修复**：删除固定 `WORKERS=1` 单线程。可用环境变量覆盖但默认必须是 1。落点：`scripts/finish.py` 顶部 `WORKERS`、SKILL.md 四.4。
- **附带**：`2>$null` 屏蔽 stderr 会让进程消失时完全没有诊断信息——stderr 一律重定向到文件保留。

### A2. 一个脚本串跑四类共用一个总预算 → 阶段连坐跳过 ★高危

- **现象**：`resume.py` 用单一 `BUDGET=540s` 从头跑四类，隔离区释放阶段把预算耗光后，retention 和 spaces 阶段被 `if STATE["hit"]: return` 一起跳过。连续多轮都卡在 release，后两类一次都没执行到。
- **根因**：预算是全局的，阶段之间有依赖（前一阶段 hit 直接 return）。release 有 18698 个文件，单轮根本删不完，于是后面永远轮不到。
- **证据**：`result.json` 显示 `partial=True, last_phase=release`，release 剩 12097 未处理；retention 14546 项 `not_found=0`（一项未动）；spaces 未开始。
- **修复**：**一次调用只跑一个 phase**，各阶段独立预算、独立结果文件 `phase_<name>.json`；一个阶段跑完才收尾。落点：`scripts/finish.py` 的 `do_release/do_retention/do_spaces` 三个独立函数 + CLI 参数选阶段；SKILL.md 四.4。

### A3. checkpoint 写了 `done` 不等于真完成 ★高危

- **现象**：`resume-checkpoint.json` 显示 `{"phase":"release_done","done":1,"total":1}`，看起来该阶段完成了，实际还有 12097 个文件没删。
- **根因**：checkpoint 的 `done=1` 是「这一批提交完毕」的标记，不是「全量清零」的标记。用它判断是否完成会得出错误结论。
- **修复**：完成判据必须是**全量回读**：`not_processed==0 && failed==0 && !hit && !interrupted`，外加批次目录 `Test-Path` 为 False。落点：`finish.py` 的 `all_processed()` + `V9` 验收；SKILL.md 四.4。

### A4. 删除进回收站，目录清零但可用空间不涨 ★高危

- **现象**：C 盘隔离批次删了 1135 MB，目录只剩 1 MB，但 C 盘可用空间从 102.752 GB 变成 102.557 GB（**反而更少**），回收站从 129 B 涨到 1932.77 MB。
- **根因**：删除保护开启时 safe-delete 把实体搬进回收站，文件还在盘上，空间没释放。
- **修复**：强制三段对账（目标目录 / 可用空间 / 回收站）；报告写「已移出隔离区，实体进回收站，需你手动清空才真正释放」，禁止写「已释放 X MB」。回收站整体是红线，不自动清空。落点：spec 2.5.3 / 2.6.3、SKILL.md 四.5、本文件 A13（官方开关）。
- **注**：`retention.guards.requireFreeSpaceIncrease` 和 `action=permanentDelete` 在策略里，但**实测仍进回收站**——不能因为写了 permanentDelete 就以为空间真释放了，必须量。

### A5. Windows 路径大小写归一化：活会话被误判为 0

- **现象**：磁盘目录是 `Claw`，会话 cwd 归一化后是 `claw`，活会话数被算成 0，差点把一个活跃空间当成已删候选。
- **根因**：路径比较没统一 `os.path.normcase`；Windows 文件系统大小写不敏感但字符串比较敏感。
- **证据**：修正后 `Claw` 正确显示「1 个活会话 + 有显示名 + 不在 workspaces 表」并被排除。
- **修复**：所有路径比较先 `norm(p)=os.path.normcase(os.path.normpath(p))`，映射表 key 也归一化。落点：`scan.py` 的 `norm/under`；扫描断言修正后**必须重跑扫描重新冻结计划**（否则计划本身是错的）。

### A6. 扫描路径断言 `all()` / `any()` 写反，retention 少算

- **现象**：`sessionRollback` 的三个具名子目录判定写成「每个文件必须同时位于三个子目录下」，导致 72 个会话被误判「断言失败」，retention 计划只有 235 项。
- **根因**：`all()` / `any()` 嵌套写反。正确逻辑是「每个文件落在三个子目录之一」。
- **证据**：修正后 retention 计划从 235 → 274 项。
- **修复**：改完脚本后重跑 `scan.py` 重新生成冻结计划和基线；不要沿用旧计划。**任何扫描逻辑改动都必须重扫并重冻结。**

### A7. 应用按旧路径重建同名空壳，成功判据过严导致误判失败

- **现象**：空间目录 `Move-Item` 到隔离区后，应用立刻按旧路径重建同名空目录；执行脚本把「源路径消失」当成功条件，判定为移动失败并中止后续候选。
- **根因**：11-04 实测过的应用行为（与「空间改名不能动磁盘目录名」同源），规格早有记载但执行脚本没照做。
- **修复**：成功判据只看**目标存在**；源路径重现记为 `rebuilt_shells`，**不二次移动**（否则变成两个空间），只报告「应用已重建空壳，需用户在侧边栏删除」。落点：`finish.py` 的 `do_spaces()`；spec 2.7.3。

### A8. safe-delete 删成功也抛错；后台任务触发批量确认拦截

- **现象**：`[safe-delete][SAFE_DELETE_FAIL_CLOSED]` 报错但文件已消失；后台运行的删除任务被 `SAFE_DELETE_BULK_CONFIRM_REQUIRED`（`{"count":50,"threshold":50,"scope":"turn"}`）拦住，前台 200 文件探针却正常。
- **根因**：① 守卫抛错不代表失败；② 后台任务没有可交互的审批通道，批量删除命中 50 阈值就卡住。
- **修复**：成功与否**只认 `Test-Path` / `os.path.exists()` 复核**，不看返回码；删除类任务一律前台执行，不放后台、不用无人值守。落点：`execute.py` 的 `rm_file()`、SKILL.md 四.4/六。

### A9. 平台安全限制是删除慢、耗积分、耗时间的根因（官方查证）

- **现象**：每删一个文件约 0.18 秒（5.4 文件/秒），3 万文件约 100 分钟；目录清零但空间不释放；批量删除要审批。用户反馈「消耗大量积分，占用大量时间」。
- **根因**（官方文档确认）：默认开「删除保护」（优先移回收站）+「批量删除审批」（默认 50 个一审批，且需先开删除保护）。
- **官方设置路径**：
  - `设置 → 安全中心 → 数据安全`：关「删除保护」（关后按系统删除）、关「批量删除审批」。
  - `设置 → 安全中心 → 沙箱安全 → 文件安全`：把目标路径的删除从「询问」改「允许」。
  - 输入框底部「默认权限」→「允许完全访问」：**全局开关、当前客户端所有任务生效、不跨设备、用完即关**。
- **警告**：关掉删除保护＝永久删除不可恢复，与「误删不可逆」铁律冲突；建议只对隔离目录短时开，别全局长期开。
- **不调设置也能跑**，但必须按 0.18 秒/文件规划轮次，不要试图一轮删完。

### A10. 工程小坑：编码、语法、双跑

- **`tasklist` 编码**：Python `subprocess` 用 `text=True` 默认 UTF-8 解 GBK 输出 → `UnicodeDecodeError: 0xd0`。修复：`capture_output=True` + `r.stdout.decode('gbk', errors='ignore')`。
- **PowerShell 5.1 不支持 `&&`**：用 `;` 分隔命令。
- **同一命令可能跑两次**（沙箱 + 提权）：脚本必须幂等；删除结果以回读为准，不信任报错文案。
- **僵尸锁未清**：本轮被用户中途打断，没走 finalize，`cleanup.lock`（pid 14464 已死）留在盘上。下次启动会判「僵尸锁可接管」，但交接时要主动报告。

### A11. 中途打断时 result.json 停在上一阶段

- **现象**：进程在 release 阶段被守卫杀掉前没进入 `save("release")`，`result.json` 一直停在 `partial=True, last_phase=cache`。
- **修复**：每个阶段单独落盘 `phase_<name>.json`，并加预算停止 + 阶段 `save(tag)`，预算耗尽时干净返回、保留 manifest 和批次目录下轮继续。落点：`finish.py` 的 `save()` 和 `BUDGET`。

---

## B. 历史坑（v7–v9.3 规格第 11 节已有，保留备查）

1. **11-04 事故**：删掉 5 个空壳空间后，应用重算工作空间把 `workspace-display-names.json` 整份删掉，侧边栏名字全消失。靠 `modify_backup\1.d.*.workspace-display-names.json` 恢复。**结论：删/移空间前必须字节级备份命名文件并校验 SHA256**，失败整节中止。
2. **`workspaces` 表只有 `path`/`last_opened_at`，无 `deleted_at`**：不能拿表里有行/没行判断用户是否删过空间。2.7 的「已删除」靠四条间接推断，宁可漏判不可误判。
3. **「时光杂货」案例**：0 活会话、无显示名，但 24h 内有写入 → 必须排除。「0 活会话」不等于「没在用」。
4. **「Claw」案例**（与 A5 相关）：不在 workspaces 表但有活会话和显示名 → 是活空间，注册不同步而已，绝不入选。
5. **禁止 `Remove-Item -Recurse`**：safe-delete 对非空目录 fail-closed 且会先移走部分子文件。必须三步：逐文件 → 子目录按路径长度倒序 → 删根。
6. **删文件必须逐文件，禁止管道**：`$items | Remove-Item` 在第一个异常处中断整条管道，只删 1 个还不报错。
7. **删除语句只用 `-ErrorAction Stop`**，吞错只允许在 try/catch 里。
8. **移入隔离区也不等于腾空间**：`lastSpaceQuarantineMB` 是移入量，真正释放要看 2.5 到期后的可用空间。
9. **`$HOME` 是 PowerShell 只读变量**：用 `$WB`。
10. **数据库只读**：不执行任何 INSERT/UPDATE/DELETE，查询一律 `mode=ro`。
11. **不拿间接指标归因**：可用空间受他人干扰不算证据；要证明删了就量目标目录。
12. **会话目录数 ≠ 有内容会话数**：106 个会话目录里 52 个是 0 文件空壳，只报告不删。
13. **回滚是撤销点不是正文**：删 `modify_backup` 不影响对话正文，但不可逆，宁可延后一轮也不误删活跃会话。
14. **报告里不出现工具内部细节**（脚本路径、临时文件名）。
15. **禁止对 `.workbuddy` / `E:\WorkBuddy` 整体 `-Recurse` 扫描**：14 万文件 / 5 GB 会卡死任务。单目录顶层项 >5000 按日期子目录分批，每批 ≤2000。

---

## 速查：这次改动对应的规格条款

| 坑 | 对应规格 / 脚本落点 |
|---|---|
| A1 并发锁 | `finish.py` WORKERS=1；SKILL 四.4 |
| A2 全局预算 | `finish.py` 分阶段 CLI；SKILL 四.4 |
| A3 checkpoint | `finish.py` `all_processed()`；V9 |
| A4 回收站 | spec 2.5.3 / 2.6.3；SKILL 四.5 |
| A5 大小写 | `scan.py` `norm()`；重扫重冻结 |
| A6 断言写反 | `scan.py` 路径断言；重扫重冻结 |
| A7 空壳重建 | `finish.py` `do_spaces()`；spec 2.7.3 |
| A8 抛错/后台 | `execute.py` `rm_file()`；spec 11 |
| A9 安全限制 | SKILL 六；官方文档 |
| A10 编码/双跑 | `status.py` GBK；SKILL 四.1 |
| A11 中断快照 | `finish.py` `save()`；SKILL 四.4 |
