# 收尾归属表（唯一主本）

> 一个事实只写一处，别处只留指针。改规则只改这一份；卡片技能与收敛技能都只读它。
> 2026-11-10 用户拍板：两个技能**不合并**，收尾统一到同一个 Stop 时刻。

## 一张表

| 信息类型 | 唯一落点 | 谁写 | 时机 |
|---|---|---|---|
| 项目状态、进度、本轮做完的事、踩过的坑、待办 | 项目卡 `~/.workbuddy/cards/<slug>/`（主卡＋分册＋事件流） | `my-project-card/card.py add` | 每轮收尾（Stop 守卫拦一次补卡） |
| 换个会话、光看代码推不出来的长期口径与偏好 | 空间 `.workbuddy/memory/MEMORY.md`（≤3000 字符 / ≤70 行） | 收敛 A 档 | **只在出现新口径时**；不为凑格式整篇重写 |
| 过程、实测数字、提交号、坑明细与场景 | 当天日志 `.workbuddy/memory/YYYY-MM-DD.md` | 收敛 A 档 | 有产出的任务收尾，只写结论不写过程 |
| 本轮新建的中间产物 | **不写进任何记忆**，只进待删清单和台账 | `wrap_cleanup.py` | Stop 时刻自动，首次 dry-run |
| 压缩记忆、归档旧日志/草稿脚本、3 天到期清理、回滚点 | 收敛 B 档 / `ttl.py` | 用户说「收敛 <空间名>」 | 低频，攒够触发条件才做 |

**同一件事不许写进两处**。上一轮实测踩过：同一结论同时写进卡片、MEMORY.md、当天日志，等于三份要维护的副本；按上表只写卡片，其余两处最多留一句指针。

## 收尾链（同一个 Stop 时刻，两个脚本互不耦合）

1. `my-project-card/scripts/stop_guard.py`：当前空间有卡 ＋ 本轮改了文件 ＋ 本轮没写卡 → 输出 `continue:false` 拦一次，把补卡命令塞回对话。补完卡第二次自动放行，被提醒后仍没补卡记 `miss`。
2. `workspace-converge/scripts/wrap_cleanup.py`：只读扫描本轮新建的中间产物 → 首次强制 dry-run 出清单 → 第二次起按白名单自动删（单轮 ≤10、删前备份并校验 sha256、写 ledger、幂等）。
3. 上表第 2、3 行**只在出现新口径或有交付物时写**；纯问答、讲概念、只读分析一律不写记忆。

两个脚本并列挂在 `~/.workbuddy/settings.json` 的 `hooks.Stop`，各自 fail-open、各自有总开关，一个出错不拖累另一个。**不要把它们合成一个脚本**：一个是提示模型补记录，一个是执行不可逆删除，失败模式不同。

## 删除的硬规矩

- 助手**不自己删文件**，删除只由 `wrap_cleanup.py` 执行；模型最多列清单。
- 白名单只认：`__pycache__` 等缓存目录内容、`*.pyc/*.pyo/*.tmp`、带 `tmp_/test_/parse_/diag_` 前缀的 json/html/xlsx/log/out。
- 一律 pin：交付物扩展名、>1MB、被引用、路径越界、`.workbuddy/`、仓库资产、个人目录（Desktop/Downloads/Documents 等）、盘符根、拿不准的。
- 首次运行**零删除**，只出清单 `<空间>/.workbuddy/archive/wrap-首次清单.md` 并写 `armed: true`；从第二次起才真删。
- 台账 `<空间>/.workbuddy/archive/wrap-ledger.md`（含 sha256）；备份 `~/.workbuddy/archive/wrap-cleanup/backup/`；判定日志同目录 `wrap.log`。
- 一键停用：新建空文件 `~/.workbuddy/.wrap-cleanup-off`，删掉即恢复。
- 台账不是恢复源，删除不可逆；本机回收站两条路都被拦，只能从备份目录还原。

## 生效前提

`settings.json` 外部修改**不热加载**，当前会话用启动快照。改完 hooks 要重启 WorkBuddy 或在 `/hooks` 面板审阅。

换机重注册：在 `~/.workbuddy/settings.json` 的 `hooks.Stop` 追加下面这一条，保留原有 tdrive 与 `stop_guard.py` 两条（本机 2026-11-10 已挂好，共 3 条）：

```json
{"matcher": "", "hooks": [{"type": "command", "command": "\"C:/Users/Administrator/.workbuddy/binaries/python/versions/3.13.12/python.exe\" \"C:/Users/Administrator/.workbuddy/skills/workspace-converge/scripts/wrap_cleanup.py\"", "timeout": 15, "metadata": {"managed_by": "workspace-converge", "description": "收尾清理：Stop 时刻按白名单清本轮新建中间产物（首次 dry-run，之后自动删并留台账，fail-open）"}}]}
```

`matcher` / `metadata` 与本机原有 tdrive、`stop_guard.py` 两条 hook 的结构保持一致，别只写 `hooks` 一个字段。

换机后 Python 路径和账号目录可能不同 → 先照本机已有 hook 的 `python.exe` 路径替换，**别照抄账号名**。改前先备份 `settings.json`；改后回读校验「非 hooks 键、SessionStart、SessionEnd、原有 Stop 条目」都没变，再确认 `wrap_cleanup.py` 只有 1 条挂载（幂等）。
