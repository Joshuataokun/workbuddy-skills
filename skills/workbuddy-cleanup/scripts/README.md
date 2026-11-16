# 脚本用法

四个脚本，对应「扫描 → 对账 → 分阶段执行 → 收尾」。**只读脚本随便跑；执行脚本会真删，务必先只读对账确认。**

## 环境变量

| 变量 | 默认 | 作用 |
|---|---|---|
| `WB_CLEAN_HOME` | `C:\Users\Administrator\.workbuddy` | WorkBuddy 数据根 |
| `WB_CLEAN_EW` | `E:\WorkBuddy` | 空间与 E 盘隔离根所在 |
| `WB_CLEAN_WORKDIR` | `<技能目录>/../.work` | 工作目录（scan.json / 基线 / 冻结计划结果 / phase 快照） |
| `WB_CLEAN_AUTOMATION_MEMORY` | 空（不写） | 定时任务 memory.md 路径；定时任务已删就别设 |
| `WBV93_BUDGET` | `480` | 单阶段单轮预算秒数（前台 600s 超时留余量） |

续跑 2026-11-16 的半截现场要指向旧工作目录：`export WB_CLEAN_WORKDIR="C:/Users/Administrator/AppData/Local/Temp/wbv93"`（Windows 用 `set` 或 PowerShell `$env:`）。

## 标准顺序

```bash
# 0. 启动锁：扫前写 $WB\cleanup.lock = {"pid":...,"startedAt":...,"host":...}
#    有效锁且 pid 存活 → 跳过；僵尸锁接管；结束必删（finish.py finalize 会删）

# 1. 只读扫描 + 冻结四类计划（绝不删）
python scan.py
#   产出：$WB\cleanup-runs\plan-<ts>.json / release-<ts>.json /
#         retention-<ts>.json / spaces-<ts>.json
#   产出：<workdir>\scan.json / baseline.json
#   注意：改过扫描断言必须重跑本步重新冻结，不能沿用旧计划（pitfalls A5/A6）

# 2. 只读对账（随便跑，确认计划与磁盘一致）
python status.py

# 3. 分阶段执行：一次只跑一个阶段，跑完一个再跑下一个
python finish.py release      # 可在多轮里反复跑，幂等，每轮独立预算
python finish.py retention
python finish.py spaces
#   每段产出 <workdir>\phase_<name>.json；单线程、逐文件、独立预算
#   完成判据：phase.complete == true（全量回读 remain=0 + 目录 Test-Path=False）

# 4. 收尾：验收 + 写运行记录 + 更新 state + 删锁
python finish.py finalize
#   产出 <workdir>\final.json；结果在对话里报告，不写报告文件到工作空间
```

## 关键约束（改脚本前先读 pitfalls.md）

- **执行脚本会真删**。动手前先 `status.py` 看 planned/remain/missing，确认没跑偏。
- **单线程**（`WORKERS=1`）：并发会触发 safe-delete 全局锁竞争被杀进程（A1）。
- **一次调用一个阶段**：一个脚本串跑四类共用一个预算会导致后面阶段永远轮不到（A2）。
- **不要后台跑删除**：无人值守会触发 `SAFE_DELETE_BULK_CONFIRM_REQUIRED` 卡住（A8）。
- **完成看回读不看 checkpoint**：checkpoint 的 done 只表示「一批提交完」，不表示全量清零（A3）。
- **删除进回收站，目录清零 ≠ 空间释放**：三段对账，报告不写「已释放 X MB」（A4）。
- **stderr 重定向到文件**，别用 `2>$null`：safe-delete 抛错但已删也算成功，出错时要有据可查（A1/A8）。

## 已知缺口（交接状态）

- `execute.py` 是早期「一次性全执行」版本，保留作函数库（提供 `under/norm/rm_file/verify_item/rm_empty_dirs/dir_stat/disk_snapshot` 等），**不要再直接用它整批执行**——它有全局预算连坐问题（A2）。执行入口统一走 `finish.py`。
- `finish.py` 的 `do_finalize()` 里 V9/V10 验收依赖 phase 完成标志；如果某阶段没跑完就 finalize，对应验收会 ✗，如实报 PARTIAL，不要手工改标志。
- 本轮（11-16）被用户中途打断，release/retention 未跑完、锁未删，见 SKILL.md 第八节。
