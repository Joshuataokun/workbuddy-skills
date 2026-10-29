# 已删除技能存档

这里放的是从 `~/.workbuddy/skills/` 移除、但**以后可能重新用上**的技能。

`sync.sh` 只镜像同步 `skills/` 目录，**不会动这里**，所以这些副本会一直留在仓库里。

## 内容

| 目录 | 原类型 | 文件数 | 删除原因 | 删除日期 |
|---|---|---|---|---|
| `grill-me/` | 本地技能 | 2 | 英文触发词 "grill me"，用户不会这么说，中文也无对应说法 | 2026-10-29 |
| `wps-office-suite__skillhub/` | 市场技能 | 58 | description 1058 字符超限 34（上限 1024）；功能已被内置能力覆盖（表格→openpyxl 脚本、PPT→ppt-generator、公文→内置 docx） | 2026-10-29 |

## 怎么恢复

把目录整份拷回技能目录即可，程序下次启动会重新扫到：

```bash
cp -r archive/deleted-skills-20261029/grill-me ~/.workbuddy/skills/
cp -r archive/deleted-skills-20261029/wps-office-suite__skillhub ~/.workbuddy/skills/
```

注意两点：

1. **`wps-office-suite__skillhub` 是市场技能**，目录名带 `__skillhub` 后缀、目录内有 `_skillhub_meta.json`。直接拷回去要恢复成市场安装态，建议改用平台的市场搜索重新安装，比手工拷干净。
2. **`grill-me` 是本地技能**，拷回去就能用。想让它以后能触发，先把 description 里的 `"grill me"` 换成中文说法。

## 恢复前先看这段

删之前记录的**使用数据**（来自 `skill-picker.json` 的 `recentlyUsedSkills`）：

- `grill-me`：零使用
- `wps-office-suite`：零使用

两者装了一个月，一次都没被真实调用过。恢复前先想清楚这次为什么觉得会用上——如果答案还是"以后可能"，那它大概还会躺一个月。
