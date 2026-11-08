# 栈识别对照表（stack-guide）

新网单到手第一步：花 10 分钟认栈，之后的排查入口全由栈决定。

## 一、H5 引擎识别（看 index.html / 产物特征）

| 引擎 | 特征 |
|---|---|
| **Cocos Creator** | `src/settings.<hash>.js`、`assets/{main,game,internal,resources}/`、bundle 名 `index.<hash>.js`+`config.<hash>.json` 成对、`cc._RF.push` 模块标记、可能 .jsc 加密 |
| **Egret（白鹭）** | `manifest.json`、`egret.min.js`、`main.min.js`、`resource/` 目录、`.exml` 皮肤、`.ths`/`.json` 资源清单 |
| **Laya** | `index.js` 内 `Laya.init`、`bin/h5/` 结构、`.json` 场景、`laya.core.js` |

Cocos 最常见（本方法论主战场，h5-patch.md 即为此写）；Egret/Laya 的 patch 思路相同（版本号绕缓存+成对资源），具体控件名体系不同。

## 二、服务端栈识别（看目录/进程/启动脚本）

| 栈 | 识别特征 |
|---|---|
| **Go** | 源码 `go.mod`/`.go`、二进制单文件无后缀、`cmd/` 入口结构、编译命令 `go build`；逆向私服常见（单二进制部署方便） |
| **C++** | `CMakeLists.txt`/`Makefile`、`.so` 依赖、lib 目录；大型端游系（azerothcore/kbengine/rathena 类） |
| **Java** | `.jar` 包、`start.sh` 里 `java -jar`、tomcat/jetty；L2J 系 |
| **Lua/skynet** | `skynet` 目录、`.lua` 脚本、agent 模型；手游服常见 |
| **Node.js** | `package.json`、`node_modules`、`app.js`；colyseus 类 |
| **PHP+混合** | ThinkPHP/Laravel 目录 + 游戏服务端二进制组合（后台/代理站常是 PHP） |

辅助判断：`ps -ef | grep -v grep`（看进程名）、`systemctl list-units`（服务单元名）、启动脚本 `cat /data/qd.sh` 类。

## 三、常见组合（H5 网单全景）

```
Cocos H5 + Go 逆向服务端 + MySQL + Redis + Nginx 静态/反代   ← 本方法论原生场景
Cocos H5 + C++ 服务端 + MySQL
Egret/Laya + Java(spring/netty) + MySQL
Cocos H5 + Node(colyseus/express) + MongoDB
+ PHP 运营后台（GM/CDK/代理）+ 可选 battlefield/battle 独立战斗服
```

典型端口布局参考：网关 28080/29999（WS/TCP）、logic 9090+运营 18091、HTTP 81（H5）/8080（后台）。**新网单先 nmap/ss 摸清端口再对号入座**。

## 四、数据流三链摸底模板（记进新空间 MEMORY）

```
登录链：客户端 → [登录方式 WS/HTTP] → 网关 → 账号库哪个表 → 角色选择
命令链：客户端命令名 → 服务端 handler 函数 → 响应结构 → 客户端消费字段
存储链：L1 内存缓存 → L2 Redis（key 模式）→ MySQL（表/json 列）→ 谁是权威源
```

每条链的第一批关键发现（编译命令、Redis key 模式、表结构、日志位置）都是新空间 MEMORY 的第一批内容。

## 同游戏生态的另一支栈（2026-11 调研补充）

咸鱼之王私服生态主流是 **skynet(Lua) + openresty + Go 管理后台** 结构（社区教程常见：openresty 前置、skynet 跑 login/game 两个服务、独立 goserver 后台 85 端口、MySQL/Redis/mongo 走 docker）。本项目的 Go 逆向服务端（gate+logic+switch+battlefield 四件）是另一支实现——**同一游戏的两种私服栈，命令协议可能同源**：社区 skynet 版的协议分析成果（如 y-projects/xyzw_analyzer）对 Go 版排查同样有参考价值。接手同类项目先看进程列表判断是哪支：skynet 进程名特征 vs Go 二进制名。
