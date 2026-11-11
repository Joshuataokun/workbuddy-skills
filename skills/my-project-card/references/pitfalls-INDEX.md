# 跨空间高危坑索引

<!-- inject: 8 -->
<!-- 本文件是 SessionStart hook 的数据源：每会话开始注入前 8 条。
     维护规则（卡片技能收尾）：复发≥2 或跨空间适用的坑才进这里；
     每条必须写「场景」——什么情况下该想起它；
     已在用户级记忆里的坑不进（避免重复注入）。
     格式：### [分类] 短名 → 场景一行 → 做法一行
     注入只取前 8 条，新增高危坑请插到本注释块之后（网游单机 2026-11-09 晋升 3 条）。 -->

### [部署] 改 Go 源码不等于上线
- 场景：改完服务端源码、单测全绿就以为线上已生效时
- 做法：必须重编译替换二进制；验线上=journalctl code + /proc/pid/exe 内含命令串 + 源码 mtime 早于二进制
- 来源: 网游单机 2026-11-08 竞技场 0-0 | 复发: 1

### [静态资源] gzip 必须带 -k
- 场景：nginx gzip_static on 的站点重新生成 .gz 时
- 做法：`gzip -k -f` 保留原文件，不带 -k 会吞掉源文件；改完 curl 双路验 plain 与 gz
- 来源: 网游单机 2026-11-08 H5 | 复发: 1

### [版本化配置] 换号要复制全部文件
- 场景：新建版本化配置目录、把 version.json 指向新号时
- 做法：复制旧目录全部 *.json，别只复制「完整包判定」那几个；换号后逐个 curl 200 + json.load 验
- 来源: 网游单机 2026-11-09 登录卡加载 | 复发: 1

### [Python正则] heredoc 吞反斜杠
- 场景：要在 Bash heredoc/python -c 里写含 `\s` `\d` 的正则或替换时
- 做法：复杂正则先写成 .py 文件再执行，禁止 heredoc 内联
- 来源: skills-dev 高频坑 | 复发: 2

### [Python正则] 判盘符用 AST
- 场景：要判断脚本里有没有"写死盘符路径"时
- 做法：用 AST 遍历字符串常量，禁用朴素正则——`http://` 的 `//` 会被误判成盘符（已两次实踩）
- 来源: skills-dev | 复发: 2

### [openpyxl] 公式读出来是 None
- 场景：openpyxl 读含公式的 xlsx、`data_only=True` 拿到 None 时
- 做法：自己求值（或用 check_ledger.py 的求值器）；求值失败报"无法求值"，绝不当 0——静默 0 = 假通过
- 来源: 台账 2026-10-26 | 复发: 1

### [git] checkout 会吃掉未提交新文件
- 场景：想用 `git checkout -- .` / `git restore .` 回滚时
- 做法：先 `git reset` 再 checkout，否则已 add 未 commit 的新文件被还原丢失
- 来源: skills-dev 高频坑 | 复发: 1

### [GitHub] 连接器只读
- 场景：想让助手用 GitHub 连接器建仓库/推大文件时
- 做法：`create_repository` 返 403（只读）；`push_files` 过不了 1.5 MB → 走本地 git+GCM（sync.sh）
- 来源: skills-dev | 复发: 1

### [Excel体量] 字节数冒充字符数
- 场景：量记忆/文档体量、判断是否超预算时
- 做法：Python `len()` 数字符；`wc -c`/文件大小是字节，中文会放大约 3 倍（曾把 2973 判成 4937）
- 来源: skills-dev | 复发: 1

### [体积测量] du 是块大小
- 场景：报文件/目录体积时
- 做法：`find -printf "%s"` 累加实际字节；du/ls 按块算会把 86 KB 报成 71 KB
- 来源: skills-dev | 复发: 1

### [编码] 管道stdout默认GBK
- 场景：脚本输出会被宿主程序捕获（hook 注入、自动化、MCP）且含中文时
- 做法：`sys.stdout.buffer` 显式写 UTF-8 字节；文本层 write 在 hook 宿主默认 cp936 必乱码
- 来源: skills-dev 2026-11-08 | 复发: 1

### [Windows] PowerShell 执行策略
- 场景：在 Bash 里调用 PowerShell 跑 .ps1 脚本时
- 做法：必须 `-ExecutionPolicy Bypass -File`；本机 PS 是 Restricted。且 Bash 里禁调 PS（编码坑），反操作用 PS 工具
- 来源: 环境空间 | 复发: 1

### [回收站] 两条路都被拦
- 场景：想用回收站 API（VB FileSystem / Shell.Application COM）删东西时
- 做法：都会被沙箱拦截 → 工作区产物只能 `rm -rf`（永久）；删前必须确认有副本，个人目录另有专门规矩
- 来源: 环境空间 | 复发: 1

### [SSH] heredoc 多层转义炸 bash
- 场景：SSH 远程执行内联脚本、嵌 node -e / python -c 时
- 做法：复杂脚本本地写好 scp 上传再执行，别远程 heredoc 套引号（时光杂货部署实踩）
- 来源: 学习捕鱼H5 2026-11-04 | 复发: 1

### [SQL] JSON 路径里的 $ 被 bash 展开
- 场景：命令行里写含 `$` 的 SQL（JSON_EXTRACT 路径）时
- 做法：SQL 写进文件再执行，禁止 SSH 内联；profile 列 binary 字符集要先 CONVERT utf8mb4（报 3144）
- 来源: 时光杂货 2026-11-07 | 复发: 1
