# H5 客户端 patch 铁律（Cocos Creator 产物结构）

沉淀自 Cocos Creator 2.x/3.x H5 游戏 + Nginx 部署实战。适用：改前端逻辑、隐藏入口、灭红点、改文案、修渲染。

## 一、先解包还是硬 grep？

- **先试 cc-reverse**（`npm install -g cc-reverse`，见 tools.md）：能把编译产物还原成源码目录结构（脚本恢复成 .ts 文件、JSC 自动解密、CCON 资源解码），分析效率比在 17MB 单文件压缩 js 里 grep 高一个数量级
- cc-reverse 跑不动（非标准结构/加壳）再退回**直接 grep 压缩 js**：按 `模块名: [ function` 定位模块、按 UI 控件名（m_xxx）定位渲染代码、按文案 key 定位语言表引用
- 大文件 grep 用 python 逐段读，shell grep 对超长行会截断

## 二、Cocos H5 产物结构（典型）

```
/webroot
├── index.html                入口（引用 settings.<ver>.js）
├── src/settings.<ver>.js     版本钉死处（game:"<bundle版本>"）
├── assets/
│   ├── main/                 登录/注册 bundle（index.<ver>.js + config.<ver>.json 成对）
│   ├── game/                 游戏 bundle（同上成对）
│   ├── internal/             引擎内部 bundle
│   └── resources/            动态资源
├── webstatic/data/<hash>/    配置数据（config.json / language.json / config_ap.json）
└── __h5_version.json         版本自检（APK 判断走网络/离线的依据）
```

要点：
- **每个 bundle = `index.<ver>.js` + `config.<ver>.json` 成对**，换版本必须成对复制，漏 config 报「资源包加载失败」
- 登录/注册代码在 `assets/main/`（不是 game bundle）
- 版本以 **index.html 实际引用**为准，不要信记忆里的版本号

## 三、patch 发布四件套（漏一步白改）

```
1. 复制 index.<旧>.js + config.<旧>.json → 新版本名（index.新.js）
2. patch 新文件（python 精确替换，assert count==1 保证唯一 + assert 锚点在目标模块区间内保证改对地方，见铁律 4）
3. 复制 settings.<旧>.js → settings.<新>.js，改 game:"<新>"
4. index.html 的 <script src> 指向新 settings
```

发布后：`node --check` → `gzip -kf` 生成 .gz → 触发/重建版本自检文件 → `curl` 端到端验证（首页引新 settings → settings 指新 bundle → 新 bundle HTTP 200）。

## 四、四条铁律（都是实战血泪）

### 铁律 1：patch 后必须 node --check
压缩 js 一个语法错误 = 全服卡在加载页。服务器没 node 就先装（npmmirror 下二进制放 /tmp 即可）；**/tmp 重启即失**，下次用时先确认存在。

### 铁律 2：逗号表达式中间只能插表达式
混淆代码常见 `a = x, b = y, c = z`（一条语句多赋值）。往中间插 `try{}catch{}` / `if` / `for` 这类**语句** = SyntaxError。只能用：
- `条件 && (表达式)`
- `条件 ? a : b`
- IIFE：`(function(){...}).call(this)`

语句级位置（分号后、return 前）才能用 try。插错位置的症状：node --check 立刻报错，但别等报错才检查——**先想清楚插入点是表达式还是语句**。

### 铁律 3：紧急修复也是发布，必须换版本号
抢修时最容易「改个文件而已」思维短路。**只要动了 bundle 内容就是发布，四件套走全。** 用户浏览器 30 天 immutable 缓存里还是旧文件，你不换名字他刷到的就是坏的（曾因此让用户二次卡死）。唯一例外：**回滚**才用旧版本号（正是要拉旧缓存）。

### 铁律 4：锚点必须验证所属模块（needle 唯一 ≠ 改对地方）
同名机制的代码在多个相似类里各有一份拷贝（如胜利/失败结算弹窗各一份 `autoCloseTimer`），压缩后变量别名不同（d/c/g/T vs c/h/y/d）。`src.count(old)==1` 只证明**唯一**，不证明它在目标模块里——实测事故：拿失败弹窗的锚点去打「胜利面板补丁」，唯一性断言通过、日志自报已修复，实际胜利路径从未被修，同一 bug 次日复发。

防重演：patch 前 `assert 目标模块起点 < 锚点位置 < 下一模块边界`（模块定位用 `模块名: [ function`）；改完验证目标模块**区间**（而非全文件）含新 needle；排查报告引用模块名原文，不能只写意图。

## 五、gzip_static 陷阱

Nginx 配了 `gzip_static on` 时：**同名 .gz 文件存在就直接返回**，你改了源文件不重新 gzip = 改动不生效。每次改完必须 `gzip -kf`。若有每分钟同步脚本（h5_gzip_sync.sh 类）也要确认它同步的是新文件。

**`gzip -f` 不带 `-k` 会删掉原文件**（只剩 .gz）：不支持 gzip 的请求直接 404，属于发布事故。标准命令 `gzip -kf`；已经被吞就用 `gunzip -k <文件>.gz` 恢复，并 curl 双路验 plain+gz 都 200。

## 六、版本自愈机制

很多 H5 站有 `__h5_version.json` + 定时自检脚本（version_check.sh），被篡改/损坏会自动恢复。APK 混合壳靠它判断走网络还是离线资源。改版本后要**主动触发一次自检脚本**重建该文件，否则可能被旧值自愈回去。

## 七、红点/入口屏蔽三板斧

1. **灭红点**：找到红点 judge 函数（`judgeXxxRed = function`），改 `return !1`——只灭红点不动功能，最安全。注意红点是树（子红点冒泡到父红点再到导航按钮），要封父 judge 才灭得干净
2. **藏入口**：列表渲染 filter 加 `&& e !== ModuleType.XXX`；按钮显示条件改恒 false；服务端 ModuleConf 的 hide/condition 通常封不住（启动补丁会清空 condition），别白忙
3. **封命令**（配合服务端）：命令前缀进服务端 disabledPrefixes 类封禁表，客户端再点也只拿到空 schema

## 八、改完的验证动作

- `curl 首页` → 应引用新 settings
- `curl settings` → 应指向新 bundle 版本
- `curl -I 新bundle.js.gz` → 200 + Content-Encoding
- `python 读新文件 data.find(老代码段)` → 0 残留（shell grep 带换行的中文文本会误报，用 python 复验）
- 让用户 F5 后实测界面

## 九、APK 混合壳（可选分发）

H5 游戏可打离线混合包 APK 直连服务器 81 端口。构建签名用 uber-apk-signer（在用户级 bin：`C:\Users\Administrator\.workbuddy\bin\`），命令 `java -jar <jar> -a in.apk -o out --allowResign`，**绝不能加 --skipZipAlign**（targetSdk≥30 必须 4 字节对齐，否则装机报 -124）。原生壳在某些模拟器死锁，兼容性优先选混合壳。

## 十、服务端+客户端联动发布（行为断层警告）

改服务端结算/协议行为时，**旧缓存客户端 + 新服务端 = 行为断层**。实例：服务端改为「等客户端上报结算」，30 天缓存里的旧客户端不会上报 → 赢了不推层，看起来像新 bug。凡服务端行为依赖客户端版本的改动：

1. 先发客户端新版本（四件套走全，新行为代码在新 bundle 里）
2. 明确要求用户 **F5 强刷后再登录**——登录页还指着旧 settings 就拿不到新 bundle，游戏包要登录后才加载
3. 服务端切换放在客户端覆盖确认之后；灰度期可在服务端保留旧路径兼容（如新客户端上报才走新逻辑，旧客户端无上报则拒绝并提示刷新）

## 十一、跨函数标志传递（battleUIData 挂自定义字段）

改「按钮按下时的行为要在另一个回调里生效」（如跳过按钮的语义改判定依据），不需要全局变量：**battleInputData 对象在面板生命周期内同一引用**，按钮回调里 `o._myFlag = ...`，battleEnd 回调里读 `e._myFlag`（e 就是同一个 battleUIData，含 battleData/options/battleResult），用完置 false 防残留。压缩代码里注意：判标志用 `!0 === e._myFlag`（防 undefined 混入），写值用布尔字面量。

实例（塔跳过改纯战力判断，用户定稿语义）：跳过按钮点击时（仅 mode=tower）记 `_towerSkipWeak = 左方.power < 右方.power`，battleEnd 上报前 `_towerSkipWeak===true` 则强制 isWin=false（不看引擎自演结局）；正常看完动画不受影响（引擎实际结局=阵容好低战力也能过）。战力数据直接读 battleData.leftTeam/rightTeam 的 power 字段（服务端下发即有）。
