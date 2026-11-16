# cleanup-policy.json 字段说明

> 唯一策略源：`C:\Users\Administrator\.workbuddy\cleanup-policy.json`（当前版本 3，updatedAt 2026-11-09）。
> **改这里等于改行为，不用改技能或脚本。期限数字一律从策略读，绝不写死在代码里。**

## 一、开关字段（真开关，代码必须读）

| 路径 | 当前值 | 作用 |
|---|---|---|
| `quarantine.autoRelease` | `true` | 隔离区到期是否自动释放（第二类自动动作总开关） |
| `retention.enabled` | `true` | 第三类（回滚/备份）总开关；false 整节跳过 |
| `spaceQuarantine.enabled` | `true` | 第四类（已删空间）总开关；false 整节跳过 |
| `retention.guards.noAutoEmptyRecycleBin` | `true` | 禁止自动清空回收站（红线，保持 true） |
| `spaceQuarantine.noDirectDelete` | `true` | 已删空间只移不删（红线，保持 true） |
| `spaceQuarantine.noDbWrite` | `true` | 不改数据库（红线，保持 true） |

## 二、期限字段（数字，读出来算到期）

| 路径 | 当前值 | 作用 |
|---|---|---|
| `autoDeleteWhitelist[].ttlHours` | 24 / 168 / 720 | 各缓存规则的保留小时数（日志 24h、剪贴板 168h、审计 720h） |
| `crashLogKeep` | `3` | 崩溃包只留最近 3 个 |
| `quarantine.ttlDays` | `7` | 隔离批次到期天数；到期时间取「目录名日期 00:00」与 `manifest.createdAt` 中**较晚**者 |
| `retention.classes[].ttlDays` | 三类均 `7` | sessionRollback / backupSnapshots / editHistoryIndexes 各自期限 |
| `spaceQuarantine.ttlDays` | `7` | 已删空间移入隔离区后多久由 2.5 释放 |
| `guards.activeHours` / `retention.guards.activeHours` | `24` | 活动守卫：24h 内有写入的一律不动 |
| `quarantine.releaseRecentWriteGuardHours` | `24` | 隔离批次内 24h 有写入 → 延后释放 |
| `spaceQuarantine.candidateRule.excludeIfWrittenWithinHours` | `24` | 空间目录 24h 有写入 → 排除候选 |

## 三、范围字段

| 路径 | 当前值 | 作用 |
|---|---|---|
| `autoDeleteWhitelist[].path` | logs / traces / shell-snapshots 等 | 缓存白名单，只有这些路径可自动删 |
| `quarantine.roots` | `E:\WorkBuddy\.trash-quarantine`、`C:\Users\Administrator\.cleanup-quarantine` | 只有这两个隔离根可自动释放 |
| `retention.classes[].root` / `.roots` | `workspace\sessions`、`backups`、5 类索引 | 只有这些具名路径可自动清 |
| `retention.classes.sessionRollback.scope` | modify_backup / snapfile / .modify_backup_meta | 会话下**只有这三个子目录**可删 |
| `retention.exclusions` | `[]` | 永久保留白名单（sid 前 8 位）；口令「保留回滚」写入这里 |
| `spaceQuarantine.candidateRule.maxDirMB` | `1` | 空间候选体积上限 1 MB |
| `spaceQuarantine.candidateRule.excludeDirNames` | `[".trash-quarantine"]` | 目录名黑名单 |
| `spaceQuarantine.quarantineRoot` | `E://WorkBuddy//.trash-quarantine` | 已删空间固定移到 E 盘隔离根（同盘） |
| `neverTouch` | binaries / plugins / workbuddy.db 等 16 项 | 红线清单，一个字节不许动 |

## 四、注释字段（**不是开关，代码不许读成开关**）

这些字段只是给人看的说明或授权记录，代码里**不得**拿它们作条件判断：

- 顶层 `note`
- `quarantine.note` / `quarantine.rule`
- `retention.note` / `retention.authorizedBy` / `retention.exclusionNote` / `retention.actionNote`
- `retention.guards.requireFreeSpaceIncrease`（策略里写了 true，但实测删除仍进回收站——不能据此以为空间真释放，必须三段对账，见 pitfalls A4）
- `spaceQuarantine.note` / `spaceQuarantine.authorizedBy` / `spaceQuarantine.guardNote` / `spaceQuarantine.firstRun`
- `candidateRule.note` / `guards.note` / `neverTouchNote`

**规则**：字段值来自用户授权的**历史记录**，不是运行时开关。运行时开关只有第一节那 7 个。

## 五、报告控制

| 路径 | 当前值 | 作用 |
|---|---|---|
| `report.topSpaceDirs` | `8` | 占用地图最多列 8 个目录 |
| `report.topSessionBackups` | `5` | 回滚备份 Top 5 会话 |
| `report.maxLines` | `48` | 报告总行数上限 |

## 六、状态文件（不是策略，但配套）

`$WB\cleanup-state.json` 记录上次运行结果：`lastRunAt` / `lastStatus` / `lastFreedMB` / `lastReleasedMB` / `lastRetentionMB` / `lastSpaceQuarantineMB` / `lastSpaceMap` / `quarantine.batches` / `retention.nextDue` / `spaceQuarantine.nextDue` / `history`（保留 26 条）。

注意：`cleanup-state.json` 的 `note` 仍写着 v9「目录级删除必须由用户口令发起」，**已过时**——v9.2 起回滚备份改为到期自动清、v9.3 起已删空间按方案 C 自动移隔离区。判断权限以 `cleanup-policy.json` 的开关为准，不要被这个 note 误导。
