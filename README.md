# 我的 WorkBuddy 技能仓库

**仓库地址**：https://github.com/Joshuataokun/workbuddy-skills
**内容**：8 个技能（4 个自建 + 4 个市场来源）+ 恢复脚本 + 交接说明
**更新方式**：`bash sync.sh "本次改了什么"`

---

## 两个方向，成本完全不同

| 方向 | 场景 | 需要凭据吗 | 谁执行 |
|---|---|---|---|
| **读** | 换电脑，把技能拿回来 | **不需要**（公开仓库） | 助手一条命令 |
| **写** | 改完技能，存回仓库 | 第一次要授权，之后免 | 助手一条命令 |

## 换电脑恢复

```bash
git clone https://github.com/Joshuataokun/workbuddy-skills.git
cd workbuddy-skills
bash restore.sh          # 加 DRY_RUN=1 可先演练
```

或者直接对助手说「技能丢了，从 GitHub 恢复」。细则见 `AGENT-RESTORE.md`。

## 备份（把本地改动推上去）

```bash
bash sync.sh "说明这次改了什么"
DRY_RUN=1 bash sync.sh "先看看会改什么"    # 演练，不提交不推送
PRUNE=0 bash sync.sh "保留孤儿目录"        # 不删仓库里本机已没有的技能
```

`sync.sh` 做五件事：从 `~/.workbuddy/skills` 重新导出 → **自动脱敏**（绝对路径换成 `<SKILLS_ROOT>`）→ **清理仓库孤儿**（仓库里有、本机已经没有的技能目录，默认开，`PRUNE=0` 关）→ 重建 `manifest.json` → 提交并推送。

**镜像语义**：仓库 `skills/` 是本机技能的精确镜像，本机删了仓库就跟着删。需要长期留档但不在本机的东西（如退役的第三方技能），放到 `skills/` 之外的目录（参考 `_retired/`，已 gitignore）。扫到 0 个技能时脚本会中止，防止误清空仓库。

## 为什么不用 WorkBuddy 账号同步

实测过：账号级存储只保存「装过哪些技能」的记录（名称、路径、版本），**不保存技能文件**。用户可见的云空间是「资料库」，但其技能说明里明确禁止把技能拆成文件上传充当跨设备同步。所以技能目前只能靠这个仓库带。

## 哪些技能会自己回来

| 类型 | 换机表现 |
|---|---|
| 市场技能（find-skills / ppt-generator / multi-search-plus / wps-office-suite） | 可能自动回来（凭市场 ID 重下，未在第二台设备实测）；仓库里仍存了一份兜底 |
| 自建技能（chinese-punctuation-fixer / prompt-rewrite-guard / html-shot / tuniu-cli） | **不会自己回来**，必须用本仓库恢复 |

## 目录

| 路径 | 说明 |
|---|---|
| `skills/` | 8 个技能的真实文件 |
| `manifest.json` | 技能数 / 文件数 / 字节数 / `SKILL.md` 指纹 |
| `AGENT-RESTORE.md` | 给新机器上的助手看的执行说明 |
| `restore.sh` | bash 恢复（macOS / Linux / Git Bash） |
| `restore-skills.ps1` + `RESTORE.bat` | Windows 双击恢复（备用） |
| `sync.sh` | 一键同步 + 推送 |
| `backup-skills.ps1` + `BACKUP.bat` | 重新打包本机技能（不推送） |

## 隐私说明

仓库是公开的。打包前已扫描：无真实身份证 / 手机号（`张三` 等均为途牛报文示例）、无单位名、无密钥；本机绝对路径已统一替换为 `<SKILLS_ROOT>`。`node_modules`（48 MB）不入库，靠 `npm install` 重建。

## 环境依赖

| 技能 | 依赖 |
|---|---|
| html-shot | Node.js（`restore.sh` 会自动 `npm install`） |
| chinese-punctuation-fixer | Python 3（标准库即可） |
