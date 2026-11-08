---
name: game-server-research
display_name: 网单逆向方法论
display_name_en: Game Server Research Playbook
description: Linux 服务端 H5 游戏（网单/私服）的架设、排查、修复、运营、换机部署方法论。适用于：新接手一个 Linux 服务端 H5 网单要摸底、功能不工作要排查、H5 客户端要 patch 改逻辑、玩法要封禁/解封、时间倒计时机制错乱、每日重置时点改了之后每日一次类按钮失灵、战斗结算与战斗动画结论不一致（输了显示胜利/跳过按钮语义要改/结算弹窗不点确认卡死）、统计/红点数据服务端发了客户端读不到、多端登录互踢（微信内置浏览器旧页面重连死循环空白）、里程碑奖励显示已获得但从未到账、赛季/周期口径变更、换服务器要打包快速部署、游戏数值研究（战力公式/养成线材料量级/充值渠道性价比/每元战力排序）、商店与奖池经济学（限购周期/开包期望/卡券汇率）、配置存在但入口功能不可见（客户端开关取值链）等场景。沉淀自 Cocos Creator H5 + Go 逆向服务端 + MySQL/Redis 栈的完整实战（识别栈→排查四步法→H5 patch 铁律→时间机制→战斗结算架构→发奖链三查→周期迁移→数值商店经济学→验证纪律→止损原则→部署包打包）。不适用于：通用软件二进制反编译（那是 reverse-engineer-anything 的领域）、单机游戏修改、有官方文档的正常开发。当用户提到 网单、私服、H5游戏服务端、开服、架设游戏、游戏排查、游戏patch、封禁玩法、服务端逆向、游戏换机部署、游戏数值、充值性价比、商店奖池、功能不可见 时使用。
description_zh: Linux 服务端 H5 游戏（网单/私服）的架设、排查、修复、运营方法论。适用于：新接手一个 Linux 服务端 H5 网单要摸底、功能不工作要排查、H5 客户端要 patch 改逻辑、玩法要封禁/解封、怀疑时间倒计时机制错乱、GM 后台与数据库联动等场景。沉淀自 Cocos Creator H5 + Go 逆向服务端 + MySQL/Redis 栈的完整实战（识别栈→排查四步法→H5 patch 铁律→时间机制→验证纪律→止损原则）。不适用于：通用软件二进制反编译（那是 reverse-engineer-anything 的领域）、单机游戏修改、有官方文档的正常开发。当用户提到 网单、私服、H5游戏服务端、开服、架设游戏、游戏排查、游戏patch、封禁玩法、服务端逆向 时使用。
description_en: Methodology for setting up, debugging, patching and running Linux game servers (private H5 game servers). Covers: onboarding a new H5 game server stack, diagnosing broken features, patching the H5 client, enabling/disabling gameplay modules, fixing time/countdown bugs, and GM-backend/database integration. Distilled from hands-on work on a Cocos Creator H5 + Go reverse-engineered server + MySQL/Redis stack: stack identification, the four-step diagnosis method, H5 patching iron rules, timestamp conventions, evidence-based verification, and the stop-loss principle. Not for generic binary decompilation (use reverse-engineer-anything), single-player game modding, or normal development with official docs.
version: 1.5.0
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
改库：停服→改 MySQL→Redis 全清→重启；重启后表值复原=查种子 SQL 回写
战斗：引擎本地自演（演出字段客户端零消费）→ 结算须与动画同源：有上报通道走战后上报，没有才开战即定局
弹窗：结算框没点确认=await 永久挂起死锁，复用 autoCloseTimer 扩模式门控兜底（锚点先验所属模块）
删号：全痕迹清查(双库+Redis)→dry-run 列清单→--yes 备份实删铁律六步；测试账号用完即删
加成：显示≠实战——查两端消费点（配置有+弹窗显+战斗零消费=纸面加成）；累计制配置取末行勿求和
数值：战力密度折算标尺（战力/材料单位）；渠道对比三查=单价×池子权重×限购周期（periodType 0=永久累计 1=日 2=周 3=月 4=年）；奖池代码必须全量拉完（截断读取=漏主体误判）；商店经济学=market 每日 16 选 6 限购吞吐 vs 无限抽卡出口
开关：配置存在但入口不可见=查客户端总开关三层取值链（服务器 config 字典→ops manifest→平台远程开关→默认值）；修复走 ops_defaults.json manifest 加键
验证：复刻证据（node 跑函数对照截图），不靠"应该好了"
止损：同一问题修三轮不闭环 → 关入口，不恋战
发奖：三查（入账/类型枚举/游标语义），弹窗≠到账
迁移：条件只匹配旧格式特征，"非新即旧"必误伤
搬家：部署包排除逆向参考/构建产物，IP 硬编码三处全改
```

## 合规红线（先于一切）

仅限**授权或自用研究**：自有服务器、学习目的、不分发客户端、不商用运营。涉他人版权的客户端资源不上传公开仓库。

## 一、开工三步（新网单摸底）

1. **识别栈**：H5 引擎（Cocos/Egret/Laya）+ 服务端语言（Go/C++/Java/Node/Lua）+ 存储（MySQL/Redis）——特征对照表见 `references/stack-guide.md`。**栈不同，排查入口完全不同**。
2. **搭空间记忆框架**：新空间 MEMORY 记服务器登录方式/端口/目录/编译命令等专属信息；跨游戏的通用打法靠本技能。
3. **摸三条链**：登录链（客户端→网关→账号库）、命令链（客户端 WS/HTTP 发什么命令、服务端谁处理、返回什么结构）、存储链（内存缓存→Redis→MySQL，谁是权威源——**先判 Redis 是纯缓存还是权威源**：纯缓存改库可 FLUSHDB 全清，权威源清了丢数据）。

## 二、排查四步法（「功能不工作」万能入口）

```
① 服务端 grep 命令注册（router/handler 映射）
② schema/配置 看该命令的响应结构与默认值
③ 服务端日志对照（journalctl/日志文件：客户端发了什么、服务端回了什么 code）
④ 客户端 bundle grep 消费字段（客户端到底读哪个字段、什么单位、哪个判空）
```

关键认知：**逆向仿制服务端里，命令只有空 schema + 硬编码 0 属「未实现」，不是 bug**；先分清未实现、配置错、逻辑错三类。有源码优先走源码+日志；没源码走抓包/代理（见 `references/tools.md`）。详解与案例模式见 `references/debug-playbook.md`。

「点了没反应」先分两型再动手：**灰显**（客户端置灰根本不发命令，网关日志零记录）vs **服务端拒**（命令到了、code!=0 被客户端 `.then` 静默吞，界面上毫无表现）——判据就是网关日志，别在界面上猜。

## 三、H5 客户端 patch（改前端逻辑/隐藏入口/灭红点）

核心是**版本号机制**：`/assets/*` 是 30 天 immutable 缓存，改文件必须换版本号让文件名变化强制绕缓存。完整流程（四件套+三条铁律+gzip+版本自愈）见 `references/h5-patch.md`。

铁律速记：
1. patch 完必跑 `node --check`（服务器没 node 就先装，/tmp 下的 node 重启会丢）
2. 压缩代码的逗号表达式中间只能插表达式，不能插语句
3. **紧急修复也是一次发布，必须换版本号**（最容易忘的一条，回滚才可以用旧版本号）
4. **锚点唯一 ≠ 改对模块**：同名代码在相似弹窗各有一份拷贝（变量别名不同），补丁前 assert 锚点位于目标模块区间内（详见 h5-patch 铁律 4）

## 四、时间机制（倒计时/1970 年专项）

- 下手前先定**字段单位约定**：该字段客户端是当秒用（×1e3）还是当毫秒用？找同一字段的全部消费点交叉验证
- 经典坑：格式化函数带「倒计时归一化」——落在未来时间戳区间的秒值被减成剩余秒，再按绝对日期渲染就成了 1970 年
- 服务端多发 `Unix()` 秒，但个别字段（周/月基准）客户端自己 ×1e3——发毫秒会放大 1000 倍，全服倒计时错乱
- **日切口径错位**（每日一次类玩法专项）：客户端「今天」判定常硬编码 0 点（isToday/todayTime），服务端归零改时点（如统一凌晨 6 点）后，0 点–新时点窗口内所有每日状态错位——客户端判「新一天」按钮亮、服务端判「同一天」拒绝、客户端吞错=「点了没反应」。修法：客户端加「游戏日锚」换算（now 距 0 点锚小于归零小时数则归前一天），isToday/updateTodayTime 全部走它，「剩余时间」公式在新锚点下自动正确；影响面用 grep isToday 调用点数统计
- 详见 `references/debug-playbook.md` 时间机制章

## 五、验证纪律

- 每次修复给出**可核对证据**：日志行、复刻函数输出（node 单测式验证）、界面截图对照——「部署了」不等于「修好了」
- 改客户端必须等用户**强刷（F5）后实测**，旧缓存会让人看到旧版本产生误判
- 一次只改一处；改完立即验证再改下一处

## 六、止损原则

同一问题**修三轮仍不闭环 → 停止深挖，关闭入口/回滚**。深层渲染缺陷（数据全对但界面不显示）在逆向客户端里极难根治，反复投入不如屏蔽。关闭 = 客户端隐藏入口 + 服务端封命令前缀 + 红点 judge 全灭，三层做齐防残留。

## 七、改库与重启铁律（三层缓存实战）

- **改库三步**：停服 → 改 MySQL → 清 Redis → 重启。Redis 是纯缓存层时直接 FLUSHDB（权威源在 MySQL），比逐键清稳。
- **「改表不生效」终极元凶**：建库种子 SQL 带 `ON DUPLICATE KEY UPDATE col=VALUES(col)`——**服务每次重启把表刷回默认值**。症状=改表→重启→值复原。判别法=改表重启后读表对比，被刷回就 grep 启动路径的 INSERT/REPLACE。根治=删掉种子 SQL 对手工要改的列的覆盖。
- **缓存三层链**（改数据后旧值可能在任何一层顶住）：①会话内存（重登解决）②Redis 键（FLUSHDB 解决）③启动种子 SQL 回写（最隐蔽，改代码解决）。症状横跳说明没清干净，按层全灭。
- **下发字段口径=客户端解析语义**：客户端 `parseInt(field)` 的字段服务端必须发数字字符串（发中文→界面 NaN）。改任何下发字段前先 grep 客户端消费点的解析函数。
- **statistics/statisticsTime 键名错位**：客户端统计枚举的值常是「小写冒号命名空间键」（如 `area:arena:last`），**不是枚举成员名**——服务端发帕斯卡键客户端静默读不到（次数显示恒满/红点恒亮）。CDP 直查真值：`__require('types-orange').Statistics`；服务端用别名函数把帕斯卡键镜像到冒号键，statistics/statisticsTime 两张视图同一函数一次兜住。
- **token 多端共存**（多端登录互踢专项）：逆向服常见「登录即轮换单值 token、旧端立即作废」——微信内置浏览器等挂着的旧页面被唤醒后重连死循环（12 秒被拒 29 次），界面拉不到数据=「进入后空白」，而本地静态配置的弹窗照常能弹（误导排查方向）。修法：登录不再无条件作废旧 token，进程内宽限表（旧 token 保留 24h）；踢人/同 IP 换号仍全吊销；服务重启宽限清空不影响主 token（主 token 走持久层）。判别多端场景看网关日志的 UA（WindowsWechat/XWEB 内核=微信内置浏览器）。
- **发奖链三查**（「显示已获得但东西没到账」专项）：① 入账检查——领取 handler 返回的 rewards 只进回包+NotifyReward 弹窗而全链无 applyReward=「空头支票」（客户端弹"获得 XX"资产从未加过），grep handler 所在文件的资产写入调用；② 类型枚举错位——同一 type 码服务端与客户端/官方数据语义可能不同（如 type 2 一边钻石一边金币），局部映射该链路，不动全局枚举；③ 游标语义——里程碑/等级回值必须匹配客户端换算链（如 `getById(level)→list.indexOf+1`），回「达成数」「领取行数」「配置行 id」三种都可能是错的，以客户端消费代码为准。领取游标（已领到第几档）与达成游标（积分到第几档）是两本账，**达成推导无条件覆盖领取游标=状态污染**（显示已领而奖励从未发）。
- **周期切换与存量迁移**（赛季/每日口径变更专项）：周期 key 换对齐方式（如周→天）时，存量迁移条件必须**只匹配旧格式特征**（如旧 key 日期必是周一），「非新 key 即旧」会把临近的新格式 key（昨天）也抢走，导致昨天数据无人结算——上线前用「昨天 key 有分」的测试用例锁住。变更计分口径时先审计现有积分来源（查各计分通道+抽查落库值），发现榜单积分全来自将废弃的通道，要在下轮结算前停服清零，否则会发一届不合规奖。
- **重启自愈准备**（升级/迁移前）：`systemctl is-enabled` 全查（含数据库/缓存/ntp/定时任务）+ 部署一键自检脚本（服务/端口/关键数据/近分钟报错/外网可达）——重启后一条命令定心，不用逐项手查。
- **战斗结算架构判别**（先查三件事）：① grep 客户端有无战后上报调用（Service 的 success/failure/end 类方法）；② grep 客户端是否消费服务端演出明细字段（memos/gameResults 类，0 命中=引擎本地自演）；③ 客户端引擎按 seed+双方 team 本地演算，服务端复刻模拟器只是近似——**结算与动画打架（输了显示胜利）时别去修模拟器，让结算跟随动画**。有上报 handler（tower_success/failure 类）→ 客户端 battleEnd 补上报（battleEnd 第二参数=引擎实际战果；非回放才上报；包 try/catch 防 WS 瞬断炸掉结算弹窗），服务端信任上报+待打值哨兵防重防陈旧；确认无上报通道才开战即定局。命令名规律=(Service 前缀_方法名).toLowerCase()，CDP 直调一次看网关日志即验证

## 八、换机部署与打包（网盘留全量部署包）

优化稳定后打全量包传私有网盘，换服务器照 DEPLOY.md 十分钟恢复：

- **包内容**：源码（排除逆向参考目录/构建产物 bin/旧 zip）+ 4 个生产二进制 + 客户端数据包目录 + 启停/自愈脚本 + **当时新做的 mysqldump 全量备份**（别拿清号前的旧备份）+ nginx 站点 + systemd 单元 + Redis 密码行 + DEPLOY.md。
- **DEPLOY.md 必写**：架构端口表、依赖清单、恢复步骤、**换 IP 硬编码清单**（数据库表/源码常量重编译/H5 数据包，IP 散在三处全改才通）、验证 curl、运维备忘（改库铁律/gzip 双路/日切时点）。
- **传输账**：服务器 5Mbps 是下行瓶颈（~1.2MB/s），2.1G 下载约 30 分钟；本地上行传网盘快（分传 server 2.5 分 + h5 8 分）——先下载到本地再 tdrive 分传，别在服务器上等。
- **验证**：网盘逐件核对大小一致再删服务器 /tmp 与本地中转。

## 工具箱速览

`references/tools.md`：cc-reverse（Cocos 全解包还原源码）、抓包四件（hosts 重定向/Wireshark/tcpdump/mitmproxy）、代理 tee 法、Lua/jsc 反编译、game-mitm（Go 游戏向 MITM，WS 双向改包）、Frida 注入重定向（免改 bundle）、Docker/LinuxGSM 部署参考。
