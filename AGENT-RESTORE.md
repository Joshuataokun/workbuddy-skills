# AGENT-RESTORE —— 给"任意一台新电脑上的 WorkBuddy 助手"看

> 人类看 `README.md`。这份是给 agent 的执行说明。
> 触发语："我的技能丢了 / 换电脑了，把技能找回来"。

## 一句话

从仓库 `Joshuataokun/workbuddy-skills` 取 `skills/` 目录，复制到 `~/.workbuddy/skills/`（Windows：`C:\Users\<用户>\.workbuddy\skills\`），重启 WorkBuddy。

## 步骤

### 1. 确认目标目录

| 系统 | 路径 |
|---|---|
| Windows | `C:\Users\<用户名>\.workbuddy\skills\` |
| macOS / Linux | `~/.workbuddy/skills/` |

不存在就创建。**不要**删掉目录里已有的其他技能。

### 2. 取文件（两种，任选其一）

**A. 有 git（推荐，一步到位）**

```bash
git clone https://github.com/Joshuataokun/workbuddy-skills.git /tmp/wbskills
cd /tmp/wbskills
bash restore.sh            # 加 DRY_RUN=1 可先演练
```

**B. 只有 GitHub 连接器 / MCP（没有 git 时）**

用 `get_file_contents` 读 `manifest.json` 拿到文件清单，再逐个读 `skills/<目录>/<文件>`，按原路径写到目标目录。全部文件是纯文本（.md / .py / .txt / .json），可直接以文本写入。

> 优先用 A。B 的代价是把 1.5 MB 文本过一遍上下文，只在没有 git 时用。

### 3. 校验（必做，别跳过）

```bash
cd <目标目录>
find . -name SKILL.md | wc -l     # 应为 8
```

再抽 2 个技能对照 `manifest.json` 里的 `bytes` 字段，字节数必须一致。

### 4. 补依赖

| 技能 | 依赖 | 命令 |
|---|---|---|
| html-shot | Node.js | `cd ~/.workbuddy/skills/html-shot && npm install --omit=dev` |
| chinese-punctuation-fixer | Python 3 | 无需安装，脚本用标准库 |

`node_modules` 不在仓库里（48 MB，靠 npm 重建）。没有 Node 时该技能能加载但无法执行，要如实告诉用户。

### 5. 收尾

让用户**完全退出并重开 WorkBuddy**，技能列表才刷新。然后核对：

- 技能数从 N 变 N+8（或按实际缺的算）
- `prompt-rewrite-guard` 在列表里（这是用户自己改的那份，v2.0.0）
- 无同名重复（重名会抢路由）

## 别做的事

- 不要从市场重装 `prompt-engineering-expert` 来"替代" `prompt-rewrite-guard`——那是原厂版，不是用户改过的版本。
- 不要动 `skills/` 下用户已有的其他技能。
- 不要在仓库里放 `node_modules`、`*.zip`、密钥、token。
- 不要把技能拆成文档上传到资料库充当同步（library 技能明确禁止）。

## 仓库里有什么

| 路径 | 说明 |
|---|---|
| `skills/` | 8 个技能的实际文件（4 本地 + 4 市场） |
| `manifest.json` | 每个技能的名称 / 来源 / 文件数 / 字节数 / SKILL.md 指纹 |
| `restore.sh` | bash 恢复（macOS / Linux / Git Bash） |
| `restore-skills.ps1` + `RESTORE.bat` | Windows 双击恢复 |
| `backup-skills.ps1` + `BACKUP.bat` | 重新打包本机技能 |
| `README.md` | 给人看的说明 |

## 备用：推送授权失效时

正常推送走系统 Git Credential Manager，首次授权后凭据存在 Windows 凭据管理器，之后无感。若某台机器上 GCM 不可用（报 `could not read Username`），用一次性 token：

1. 在 GitHub 生成细粒度 token：只对 `workbuddy-skills` 一个仓库，权限只要 **Contents: Read and write**
2. 推送并立即作废：

```bash
AUTH=$(printf 'x-access-token:%s' "$GH_TOKEN" | base64 | tr -d '\n')
git -c credential.helper= -c http.extraheader="AUTHORIZATION: basic $AUTH" push -u origin main
```

`GH_TOKEN` 用环境变量传入，不要写进任何文件；推完到 GitHub 上 Revoke。

## 已知边界

- 市场技能（find-skills / ppt-generator / multi-search-plus / wps-office-suite）换机通常会自己回来；仓库里仍存了一份作为兜底。
- 用户自建的 4 个技能**不会**自己回来，必须走本流程。
- 恢复后技能能用，但"用户偏好"这类记忆不在本仓库（那是另一套 memory 体系）。
