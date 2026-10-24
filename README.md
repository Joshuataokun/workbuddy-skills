# 我的 WorkBuddy 技能随身包

打包时间：2026-10-24 17:25
包含：8 个技能（4 个自建/本地 + 4 个市场来源），1.56 MB

---

## 为什么需要这个包

WorkBuddy 换电脑登录账号后：

| 类型 | 会自动回来吗 | 说明 |
|---|---|---|
| 市场技能（find-skills / ppt-generator / multi-search-plus / wps） | **可能**会 | 安装记录在账号级存储里，且能凭市场 ID 重新下载 |
| **自建/本地技能**（chinese-punctuation-fixer / html-shot / prompt-rewrite-guard / tuniu-cli） | **不会** | 技能文件只在 `C:\Users\<你>\.workbuddy\skills\` 这台机器上，没有任何上传通道。账号里只会留一条指向旧路径的死记录 |

所以本地技能必须自己带走。这个包就是干这个用的。

## 新电脑上怎么用（30 秒）

1. 把整个文件夹解压到任意位置（路径别带特殊符号）。
2. 先装好 WorkBuddy 并**登录同一个账号**，然后**完全退出** WorkBuddy。
3. 双击 `RESTORE.bat`。
4. 看到「技能处理完成: 8 个」后，重新打开 WorkBuddy。
5. 打开技能列表确认。

脚本做的事：把 old 版本备份到 `_replaced_时间戳` 目录，再拷入新版本；遇到含 `package.json` 的技能（HTML-Shot）会尝试 `npm install`，本机没装 Node 会提示但不报错。

## 只想恢复其中几个

把 `skills` 目录里不需要的子文件夹删掉，再运行 `RESTORE.bat` 即可。

## 不要带的东西

- `node_modules`：48 MB，换机后由 `npm install` 重建，包里故意没有。
- `*.zip`：旧安装包，无用。

## 以后怎么维护

改完技能后，双击 `BACKUP.bat` 重新生成一份，覆盖旧的包。

**注意**：`BACKUP.bat` 会先删掉包里的 `skills` 目录再重新拷，所以不要在包里手工放别的东西。

## 清单

详见 `manifest.json`（每个技能的名称、来源、文件数、字节数、SKILL.md 指纹）。

## 2026-10-24 的技能清单

| 技能 | 来源 | 文件数 | 说明 |
|---|---|---|---|
| chinese-punctuation-fixer | 本地 | 13 | 中文标点修复，v1.0.0，含 4 个测试 + 3 份语料 |
| prompt-rewrite-guard | 本地 | 9 | 提示词改写守门员，v2.0.0（原 prompt-engineering-expert 改造版） |
| html-shot | 本地 | 12 | HTML/URL 转图片，v1.1.6，需 node 依赖 |
| tuniu-cli | 本地 | 11 | 途牛旅行，v1.1.1 |
| find-skills | 市场 | 4 | 技能发现 |
| ppt-generator | 市场 | 20 | PPT 生成 |
| multi-search-plus | 市场 | 21 | 多引擎搜索 |
| wps-office-suite | 市场 | 58 | WPS 全家桶 |
