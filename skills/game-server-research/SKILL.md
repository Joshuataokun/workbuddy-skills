---
name: game-server-research
display_name: 网单逆向方法论
display_name_en: Game Server Research Playbook
description: Linux 服务端 H5 游戏（网单/私服）的架设、排查、修复、运营方法论。适用于：新接手一个 Linux 服务端 H5 网单要摸底、功能不工作要排查、H5 客户端要 patch 改逻辑、玩法要封禁/解封、怀疑时间倒计时机制错乱、GM 后台与数据库联动等场景。沉淀自 Cocos Creator H5 + Go 逆向服务端 + MySQL/Redis 栈的完整实战（识别栈→排查四步法→H5 patch 铁律→时间机制→验证纪律→止损原则）。不适用于：通用软件二进制反编译（那是 reverse-engineer-anything 的领域）、单机游戏修改、有官方文档的正常开发。当用户提到 网单、私服、H5游戏服务端、开服、架设游戏、游戏排查、游戏patch、封禁玩法、服务端逆向 时使用。
description_zh: Linux 服务端 H5 游戏（网单/私服）的架设、排查、修复、运营方法论。适用于：新接手一个 Linux 服务端 H5 网单要摸底、功能不工作要排查、H5 客户端要 patch 改逻辑、玩法要封禁/解封、怀疑时间倒计时机制错乱、GM 后台与数据库联动等场景。沉淀自 Cocos Creator H5 + Go 逆向服务端 + MySQL/Redis 栈的完整实战（识别栈→排查四步法→H5 patch 铁律→时间机制→验证纪律→止损原则）。不适用于：通用软件二进制反编译（那是 reverse-engineer-anything 的领域）、单机游戏修改、有官方文档的正常开发。当用户提到 网单、私服、H5游戏服务端、开服、架设游戏、游戏排查、游戏patch、封禁玩法、服务端逆向 时使用。
description_en: Methodology for setting up, debugging, patching and running Linux game servers (private H5 game servers). Covers: onboarding a new H5 game server stack, diagnosing broken features, patching the H5 client, enabling/disabling gameplay modules, fixing time/countdown bugs, and GM-backend/database integration. Distilled from hands-on work on a Cocos Creator H5 + Go reverse-engineered server + MySQL/Redis stack: stack identification, the four-step diagnosis method, H5 patching iron rules, timestamp conventions, evidence-based verification, and the stop-loss principle. Not for generic binary decompilation (use reverse-engineer-anything), single-player game modding, or normal development with official docs.
version: 1.1.0
author: Joshuataokun
tags: 网单,私服,H5游戏,服务端架设,游戏排查,客户端patch,封禁玩法,时间机制,Cocos,Go
---

# 网单逆向方法论（Linux 服务端 H5 游戏）

## 中文速览

```
开工：识别栈 → 搭记忆 → 摸数据流（登录/命令/存储三条链）
排查：grep 命令注册 → schema 看响应 → 日志对照 → 客户端消费字段
patch：四件套 + 换版本号 + node --check（紧急修复也不能免）
时间：先定字段单位约定（秒/毫秒）再动手
验证：复刻证据（node 跑函数对照截图），不靠"应该好了"
止损：同一问题修三轮不闭环 → 关入口，不恋战
```

## 合规红线（先于一切）

仅限**授权或自用研究**：自有服务器、学习目的、不分发客户端、不商用运营。涉他人版权的客户端资源不上传公开仓库。

## 一、开工三步（新网单摸底）

1. **识别栈**：H5 引擎（Cocos/Egret/Laya）+ 服务端语言（Go/C++/Java/Node/Lua）+ 存储（MySQL/Redis）——特征对照表见 `references/stack-guide.md`。**栈不同，排查入口完全不同**。
2. **搭空间记忆框架**：新空间 MEMORY 记服务器登录方式/端口/目录/编译命令等专属信息；跨游戏的通用打法靠本技能。
3. **摸三条链**：登录链（客户端→网关→账号库）、命令链（客户端 WS/HTTP 发什么命令、服务端谁处理、返回什么结构）、存储链（内存缓存→Redis→MySQL，谁是权威源）。

## 二、排查四步法（「功能不工作」万能入口）

```
① 服务端 grep 命令注册（router/handler 映射）
② schema/配置 看该命令的响应结构与默认值
③ 服务端日志对照（journalctl/日志文件：客户端发了什么、服务端回了什么 code）
④ 客户端 bundle grep 消费字段（客户端到底读哪个字段、什么单位、哪个判空）
```

关键认知：**逆向仿制服务端里，命令只有空 schema + 硬编码 0 属「未实现」，不是 bug**；先分清未实现、配置错、逻辑错三类。有源码优先走源码+日志；没源码走抓包/代理（见 `references/tools.md`）。详解与案例模式见 `references/debug-playbook.md`。

## 三、H5 客户端 patch（改前端逻辑/隐藏入口/灭红点）

核心是**版本号机制**：`/assets/*` 是 30 天 immutable 缓存，改文件必须换版本号让文件名变化强制绕缓存。完整流程（四件套+三条铁律+gzip+版本自愈）见 `references/h5-patch.md`。

铁律速记：
1. patch 完必跑 `node --check`（服务器没 node 就先装，/tmp 下的 node 重启会丢）
2. 压缩代码的逗号表达式中间只能插表达式，不能插语句
3. **紧急修复也是一次发布，必须换版本号**（最容易忘的一条，回滚才可以用旧版本号）

## 四、时间机制（倒计时/1970 年专项）

- 下手前先定**字段单位约定**：该字段客户端是当秒用（×1e3）还是当毫秒用？找同一字段的全部消费点交叉验证
- 经典坑：格式化函数带「倒计时归一化」——落在未来时间戳区间的秒值被减成剩余秒，再按绝对日期渲染就成了 1970 年
- 服务端多发 `Unix()` 秒，但个别字段（周/月基准）客户端自己 ×1e3——发毫秒会放大 1000 倍，全服倒计时错乱
- 详见 `references/debug-playbook.md` 时间机制章

## 五、验证纪律

- 每次修复给出**可核对证据**：日志行、复刻函数输出（node 单测式验证）、界面截图对照——「部署了」不等于「修好了」
- 改客户端必须等用户**强刷（F5）后实测**，旧缓存会让人看到旧版本产生误判
- 一次只改一处；改完立即验证再改下一处

## 六、止损原则

同一问题**修三轮仍不闭环 → 停止深挖，关闭入口/回滚**。深层渲染缺陷（数据全对但界面不显示）在逆向客户端里极难根治，反复投入不如屏蔽。关闭 = 客户端隐藏入口 + 服务端封命令前缀 + 红点 judge 全灭，三层做齐防残留。

## 工具箱速览

`references/tools.md`：cc-reverse（Cocos 全解包还原源码）、抓包四件（hosts 重定向/Wireshark/tcpdump/mitmproxy）、代理 tee 法、Lua/jsc 反编译、Docker/LinuxGSM 部署参考。
