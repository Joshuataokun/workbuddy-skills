---
name: my-project-card
display_name: 我的项目卡片
display_name_en: My Project Card
description: 跨会话维护一个长期项目的"主卡 + 分册"记忆。主卡放跨工作面通用的目标/口径/排除方案/进度/待办，每个工作面一个分册放各自的细节，改一个不碰其它。一次命令完成备份、写入、校验、刷新镜像并直接打印结果。当用户说"接着上次""上次做到哪了""继续上次的活"，或要求"记到卡片""更新卡片""开个分册""读卡"时使用。
description_zh: 跨会话维护一个长期项目的"主卡 + 分册"记忆。主卡放跨工作面通用的目标/口径/排除方案/进度/待办，每个工作面一个分册放各自的细节，改一个不碰其它。一次命令完成备份、写入、校验、刷新镜像并直接打印结果。当用户说"接着上次""上次做到哪了""继续上次的活"，或要求"记到卡片""更新卡片""开个分册""读卡"时使用。
description_en: Cross-session memory for a long-running project using one main card plus per-workstream sub-cards. The main card holds shared goal, constraints, rejected approaches, progress and todo; each workstream gets its own sub-card so updating one never touches the others. A single command does backup, write, validate, refresh the workspace mirror and print the result. Use when the user says "continue from last time", "where did we leave off", or asks to "save to the card", "update the card", "create a sub-card" or "read the card".
version: 1.0.0
author: Joshuataokun
tags: 项目卡片,主卡,分册,接着上次,跨会话,进度延续,工作面
---

# 我的项目卡片

一个长期项目会跨几十个会话、经历十几个工作面。旧做法的毛病是**每次改一条都要跑五步**（备份→改文件→刷新镜像→校验→再读报告），而且七段内容挤在一个文件里，改素材库也要把网页那一堆一起读一遍。

这一版改了两件事：**五步合成一步**，**按工作面拆成分册**。

## 一、结构：一张主卡 + 若干分册

```
~/.workbuddy/projects/<slug>/
├── context-card.md          主卡：目标 / 口径 / 已排除方案 / 已完成 / 进度 / 待确认 / 关键位置
├── books/
│   ├── poker-web.md         分册：职责 / 口径 / 已完成 / 待办 / 关键位置
│   ├── poker-ai-kit.md
│   └── assets.md
└── backups/                 每次写入前自动备份
<会话工作区>/.workbuddy/PROJECT_CONTEXT.md   镜像（主卡 + 分册索引，供用户直接看/改）
```

**什么进主卡**：跨所有工作面都成立的东西——项目目标、共用口径（比如"线上发布走哪个 appId"）、被否决的方案及原因、总进度、全局待办。
**什么进分册**：只对某一个工作面成立的东西——那个子项目的接口、测试命令、发版步骤、遗留问题。

判断口诀：**换一个工作面就说不通的内容，进分册；放到哪儿都成立，才进主卡。**

## 二、命令（一次调用做完所有事）

```bash
# 建卡（可同时建分册）
python card.py init --project "斗三张扑克" --slug poker-suite --books poker-web assets --workspace "<工作区>"

# 记一条（默认主卡；--book 写分册）
python card.py add --slug poker-suite --section 进度 --text "258 项测试全过" --quote "改完就跑一遍" --workspace "<工作区>"
python card.py add --slug poker-suite --book poker-web --section 待办 --text "素材转 WebP" --pending

# 读卡（只读，开局用）
python card.py resume --slug poker-suite --workspace "<工作区>"

# 看分册全文 / 体检 / 列卡 / 建分册
python card.py show --slug poker-suite --book poker-web
python card.py check --slug poker-suite
python card.py list
python card.py book --slug poker-suite --name release
```

`add` 一条命令内部依次完成：备份 → 写入 → 校验 → 刷新镜像 → 打印段计数。**不需要再读任何报告文件**，结果直接打在屏幕上。

## 三、条目标记（唯一硬规则）

```
- 【确认·YYYY-MM-DD·"用户原话"】条目正文     ← 日期必填，"原话"可选但强烈建议
- 【待确认】条目正文                          ← 没拍板的全部走这个
```

- 标【确认】却含推测词（应该／大概／估计／可能是／大概率…）→ 直接拒绝写入
- 明文密码／密钥／token → 拒绝写入，只记"凭据在哪"
- 日期在未来 → 拒绝写入
- 任何拒绝都**不改动文件**，原样保留

## 四、开工与收尾的固定动作

**开工**：`resume` → 看主卡 + 分册待办数 → 超过 `--stale-days`（默认 14 天）未更新就先跟用户核对口径，不拿旧卡直接干。

**收尾**（一次 `add` 一条，别攒）：
1. 做完了什么 → 主卡 `完成`，或对应分册 `已完成`
2. 用户新定的规矩 → 主卡 `约束`，工作面专属的进分册
3. 被否掉的方案 → 主卡 `排除`，**必须带否决原因**，否则下次还会再试一遍
4. 出现新的未决问题 → `--pending` 进 `待确认`

## 五、常见误区

- **别把细节抄进主卡**。分册里有路径就够了，主卡只留指针。主卡的价值与长度反相关。
- **别建"什么都装"的分册**。一个分册管一个工作面，超过一屏就该再拆。
- **别在没核对的情况下续用超期卡**。过期地图比没有地图危险。
- **别把推测写成确认**。写完自己念一遍：这句话能指回一句用户原话或一份文件吗？指不回就标待确认。
