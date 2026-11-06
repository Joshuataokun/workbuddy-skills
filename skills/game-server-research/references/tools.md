# 工具链清单（tools.md）

网单研究工具箱。按「有没有服务端源码」分两路。

## 一、有服务端源码（主路径）

基本靠：grep + 日志（journalctl）+ python 读大文件 + node 跑复刻验证。见 debug-playbook.md。补充：

| 工具 | 用途 | 备注 |
|---|---|---|
| **node 二进制** | `node --check` 语法校验 patch、复刻客户端函数验证 | npmmirror 下（`https://npmmirror.com/mirrors/node/`）解压即用；放 /tmp 重启丢，放 /usr/local 稳 |
| **cc-reverse** | Cocos Creator 全套解包还原 | 见下节，优先用 |
| **mitmproxy** | 偶尔需要看客户端↔服务端实际交互 | `mitmproxy --mode reverse:http://游戏服` |

## 二、无源码/黑盒（抓包代理路）

### hosts 重定向 + 抓包
```
# 客户端机器 hosts 把游戏域名指向分析机
# Wireshark/tcpdump 抓包：tcpdump -i any port 28080 -w game.pcap
# wireshark 过滤：tcp.port == 28080
```

### 自建代理 tee 法（Erlang 复活游戏方法论，最有用）
写一个透明代理：客户端 → 我的代理 → 真服务器，双向流 tee 存文件。可以**读、改、重放任意包**——比纯抓包多出主动试探能力。WS 用 node ws 库、TCP 用 Go/Python 都行，几十行代码。

### 协议帧结构分析（二进制协议）
看：魔数、版本字段、操作码、长度字段、校验和、TLV。技巧：
- 把字段值**聚合到 CSV** 看取值分布（恒定值=版本类、递增=ID 类、小范围枚举=类型码）
- 对比同一操作多次抓包的差异字段
- zlib 特征头（0x78）直接解压试

## 三、Cocos 专项

### cc-reverse（重点工具）
```
npm install -g cc-reverse
cc-reverse --path ./游戏webroot --output ./src-restored
```
- 支持 Cocos Creator 2.3.x/2.4.x/3.x 自动识别
- **JSC 加密自动解密**：XXTEA+gzip，密钥自动从 application.js / src/settings.json 抽取（也支持 `--key` 手传）
- 脚本恢复成每文件 .ts（browserify 切片 + AST 兜底，保留 cc._RF UUID）
- CCON/CCONB 二进制资源解码、Spine/DragonBones 提取
- 输出 `RECOVERY_REPORT.md`（脚本格式/资源统计/bundle 表）
- GitHub：`Crain99/cc-reverse`；配套 Claude Code 插件版 `cocos-reverse-engineering-skill`
- **先跑它，跑不动再退回硬 grep**（h5-patch.md 的路径）

### jsc 字节码（无加密但被编译时）
`zboralski/spidermonkey-dumper`：SpiderMonkey jsc 反汇编，可选接 Ollama LLM 反编译。适用 Cocos2d-JS v3.x 系。

### Lua 服（skonet 类）
unluac（Java，Lua 5.1 最佳）→ luadec 兜底 → ChunkSpy 分析字节码结构。luac 文件直接 strings 看常量也常有惊喜。

### 二进制逆向
Ghidra（免费）/IDA；找 IP/端口/密钥字符串（`strings binary | grep -E '[0-9]{1,3}\.[0-9]{1,3}'`）。dnSpy 处理 .NET。

## 四、部署运维参考

| 工具 | 适用 |
|---|---|
| **LinuxGSM**（github GameServerManagers/LinuxGSM） | 标准游戏服一键部署管理（Steam 系居多），网单参考其 systemd/监控模式 |
| **Docker** | DNF 类网单整个服务端容器化（含 MySQL），`--shm-size` 别忘调大；镜像坏了秒回滚 |
| systemd 自写服务 | 网单常态：`/etc/systemd/system/游戏名.service`，ExecStart 指二进制，日志走 journalctl |

## 五、用户级已有资产

- `C:\Users\Administrator\.workbuddy\bin\uber-apk-signer.jar`：APK 重签名（禁 --skipZipAlign）
- WorkBuddy 本身：SSH 远程执行、python 大文件处理、node 复刻验证——网单研究的主工作台

## 合规提醒

抓包/逆向/解包仅限**自用研究或已授权目标**；不解包分发他人版权客户端，不公开传播协议逆向成果。
