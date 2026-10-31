# 看着大但不能删的目录（2026-10-30 实测）

C 盘上占用最大的那几个目录，绝大多数不是垃圾。**目录体积只能当「占用证据」，不能当「清理额度」。**

下表全部逐层查过子目录结构后判定。

## 一、功能数据（删了功能就缺）

| 目录 | 体积 | 里面是什么 | 删了会怎样 |
|---|---:|---|---|
| `%APPDATA%\kingsoft\wps\addons` | 4.0 GB | WPS 插件与模板 | PDF 转换、模板库等功能缺失 |
| `C:\ProgramData\Adobe\CameraRaw` | 2.2 GB | Adobe Camera Raw 相机配置文件 | Lightroom/PS 打不开对应相机 RAW |
| `C:\ProgramData\NVIDIA\NGX` | 1.2 GB | DLSS 模型文件 | 游戏 DLSS 画质功能受影响 |
| `%APPDATA%\Tencent\xwechat\radium` | 764 MB | 微信渲染引擎（Radium） | 微信界面可能异常 |
| `%APPDATA%\Tencent\xwechat\xplugin` | 580 MB | 微信插件 | 部分功能缺失 |
| `%APPDATA%\Tencent\WeMeet\Global\Data\DynamicResource` | 189 MB | 腾讯会议动态资源 | 虚拟背景/特效缺失 |
| `%APPDATA%\Tencent\WeMeet\Global\Data\AvatarModel` | 34 MB | 虚拟形象模型 | 虚拟形象功能失效 |
| `C:\ProgramData\AnyTxt\data` | 2.6 GB | AnyTXT 全文搜索索引 | 可删，但下次搜索要重建索引（耗时） |

## 二、系统与可维护性（动了有代价）

| 目标 | 体积 | 为什么不动 |
|---|---:|---|
| `C:\Windows\WinSxS` | 12.05 GB（其中 8.14 GB 是与系统共享的硬链接） | **绝对不能手动删**，微软警告会导致无法启动、无法更新。只能用 DISM，而本机 DISM 实测 0 收益（见 SKILL.md） |
| `C:\pagefile.sys` | 6 GB | 虚拟内存，关掉或搬走影响稳定性与崩溃转储 |
| `C:\ProgramData\Package Cache` | 907 MB | VS / 运行库安装缓存，删了影响修复与卸载 |
| `%LOCALAPPDATA%\Microsoft\Windows\Explorer\*.db` | 7 MB | 缩略图/图标缓存，被 explorer 独占，不结束 explorer 删不掉，收益不抵风险 |
| `C:\Windows\Prefetch` | — | 清了拖慢程序启动 |

## 三、怎么判断一个陌生大目录能不能删

按顺序问，全过才动手：

1. **子目录里有没有明确的 `cache` / `temp` / `log` / `crash` / `update` 命名？** 只有这些是可删的，其余都是功能数据。
2. **删掉后应用还能正常用吗？** 名字带 `addons` / `plugins` / `models` / `resources` / `data` 的，基本都要保留。
3. **它是索引还是数据？** 索引（搜索库、缓存库）可删但会重建，要算重建成本。
4. **重建需要什么？** 需要重新下载几个 GB、或需要账号重新登录的，别删。
5. **有没有官方清理入口？** WPS 云缓存走 WPS「释放空间」，ESP-IDF 走 `idf_tools.py`，微信走客户端设置。

## 四、反例：这些都是真的垃圾

同样是几个 GB，这些可以删：

- `%LOCALAPPDATA%\@genieworkbuddy-desktop-updater\installer.exe` 429 MB —— 更新包残留
- `%USERPROFILE%\.workbuddy\logs`、`traces` —— 诊断日志
- `%APPDATA%\Tencent\xwechat\log` —— 微信运行日志（聊天记录不在这里）
- `%LOCALAPPDATA%\cherrystudio-updater` —— 更新包残留
- `%APPDATA%\Tencent\WeMeet\Global\Data\WebkitCacheData` —— 网页缓存

判据：**名字里带 log / cache / temp / updater / installer 的，且删掉不影响功能。**

## 五、不要被扫描器的数字带跑

`analyze.ps1` 的 `AF` 类会把整个 AI 应用目录（本机 WorkBuddy 4.02 GB）算进占用，但其中 `binaries` 1.45 GB、`workspace` 0.66 GB、`plugins` 0.46 GB **全是必需**，真正能删的只有 `logs` 398 MB + `traces` 43 MB + `installer.exe` 429 MB。

**看到 "Safe to clean" 先看它指的是哪些精确路径，不看总数。**
