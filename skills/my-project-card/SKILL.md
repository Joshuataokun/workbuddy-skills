---
name: my-project-card
display_name: 我的项目卡片
display_name_en: My Project Card
description: 多会话共享的项目状态板。一个长期项目分成几条工作线、同时开着几个会话时，让每个会话开工就知道别人正在做什么、做过什么、踩过什么坑，收尾时把结论记回卡片。主卡放跨工作面通用的目标/口径/已排除方案，每个工作面一本分册（含"踩过的坑"），并发写入有文件锁不会互相覆盖。当用户说"接着上次""上次做到哪了""继续上次的活"，或要求"记到卡片""更新卡片""开个分册""读卡""开工"，或同时开着多个会话做同一项目时使用。
description_zh: 多会话共享的项目状态板。一个长期项目分成几条工作线、同时开着几个会话时，让每个会话开工就知道别人正在做什么、做过什么、踩过什么坑，收尾时把结论记回卡片。主卡放跨工作面通用的目标/口径/已排除方案，每个工作面一本分册（含"踩过的坑"），并发写入有文件锁不会互相覆盖。当用户说"接着上次""上次做到哪了""继续上次的活"，或要求"记到卡片""更新卡片""开个分册""读卡""开工"，或同时开着多个会话做同一项目时使用。
description_en: A shared project status board for work split across several sessions. Before starting, each session sees what the others are doing, what has been done, and which pitfalls were already hit; when finishing, conclusions go back to the card. The main card holds goal, constraints, rejected approaches and progress shared by all workstreams; each workstream has its own sub-card including a pitfalls section. Concurrent writes are file-locked and never overwrite each other.
version: 2.0.0
author: Joshuataokun
tags: 项目卡片,主卡,分册,接着上次,跨会话,多会话,进度延续,工作面,踩过的坑
---

# 我的项目卡片

给**同一个项目的几条工作线**用的共享状态板。解决的不是"我一个人记不住"，而是"同时开着三个会话，A 不知道 B 刚改了什么、C 不知道 A 踩过哪个坑"。

## 一、什么时候该建卡

三条**同时**满足才建，缺一条就别建：

1. **跨会话**——这件事会持续两周以上，不是一次问完就结束；
2. **多工作面**——至少两条独立工作线（比如网页端、AI 侧、素材）；
3. **会忘**——两周后回来看，不记就想不起来当初为什么这么定。

只做一次的任务、单文件的小改动、纯问答，都不建卡。建了反而多一道动作。

## 二、结构

```
~/.workbuddy/cards/<slug>/
├── context-card.md        主卡：目标 / 口径 / 已排除方案 / 已完成 / 进度 / 待确认 / 关键位置
├── books/<工作面>.md       分册：职责 / 口径 / 已完成 / 待办 / 踩过的坑 / 关键位置
├── sessions.json          谁正在动哪个工作面（带心跳）
├── journal/YYYY-MM.ndjson 事件流：谁在什么时候记了什么，只追加不改写
└── backups/               每次写入前的快照，统一放这里
<工作区>/.workbuddy/PROJECT_CONTEXT.md   自动生成的简报，只读
```

**拆分口诀**：换一个工作面就说不通 → 进分册；放哪儿都成立 → 留主卡。

## 三、命令

```bash
CARD=~/.workbuddy/skills/my-project-card/card.py

# 建卡（可同时建分册，绑定工作区后自动生成简报）
python $CARD init --project "斗三张扑克" --slug poker-game \
  --books web ai assets --workspace "E:/WorkBuddy/2026-10-12-10-32-31"

# 开工：先读简报（默认四十行内，--full 看全文）
python $CARD resume --slug poker-game --workspace "<当前工作区>"

# 声明要动哪个工作面（可选，add 会自动登记，claim 用于提前打招呼）
python $CARD claim --slug poker-game --book web --note "在改发牌动画"
python $CARD release --slug poker-game

# 记一条（默认主卡；--book 写分册；--pending 进待确认）
python $CARD add --slug poker-game --section 进度 --text "258 项测试全过" \
  --quote "改完就跑一遍" --workspace "<当前工作区>"
python $CARD add --slug poker-game --book web --section 坑 \
  --text "ffmpeg 转 WebP 丢透明通道，要加 -pix_fmt"

# 改口径（旧条目自动标失效，不用手改文件）
python $CARD revise --slug poker-game --id a1b2 --text "发布改走 appId wx999"

# 补救：新条目替代某条旧记录
python $CARD add --slug poker-game --section 口径 --text "..." --supersede a1b2

# 查旧事 / 体检 / 列卡 / 建分册 / 清备份
python $CARD search --slug poker-game --keyword 透明通道
python $CARD check --slug poker-game
python $CARD list
python $CARD book --slug poker-game --name release
python $CARD gc --slug poker-game --keep 40
```

`add` 一条命令内部依次完成：锁 → 查重 → 备份 → 写入 → 更新事件流 → 刷简报 → 打印计数。**不需要读任何报告文件。**

改了这个技能的引擎代码，跑一遍 `python scripts/acceptance.py`（30 项，含八进程并发写同一分册）。

## 四、条目标记（唯一硬规则）

```
- 【确认·YYYY-MM-DD·"用户原话"】#id 正文
- 【待确认】#id 正文
- 【已失效·YYYY-MM-DD·被 #id 替代】#id 正文
```

`#id` 由命令自动生成，用来引用和作废，不要自己编。

- 标【确认】却含推测词（应该／大概／估计／可能是／大概率…）→ 直接拒绝写入
- 明文密码／密钥／token → 拒绝，只记"凭据在哪"
- 日期在未来 → 拒绝
- 与同段已有条目几乎一字不差 → 拒绝（要保留就加 `--force`）
- 任何拒绝都**不改动文件**，原样保留，退出码非 0

## 五、开工与收尾的固定动作

**开工**（每个会话第一件事）：

1. `resume` 看三块：谁在动哪个工作面、最近发生了什么、待办与待确认；
2. 简报里显示某个工作面正被别人占着 → 先跟用户说一声，或换一条线；
3. 主卡超过 `--stale-days`（默认 14 天）没更新 → 先核对口径再干，不拿旧卡直接上手。

**收尾**（一次 `add` 一条，别攒）：

1. 做完了什么 → 主卡 `完成`，或对应分册 `已完成`
2. 用户新定的规矩 → 主卡 `口径`；只对某条线成立的进分册
3. 被否的方案、踩过的坑 → 主卡 `排除`（带原因）／分册 `坑`（带现象和解法）
4. 冒出未决问题 → `--pending` 进 `待确认`
5. 走之前 `release`，让别的会话知道这条线空出来了

## 六、多会话并发的三条硬规矩

1. **先读后写**。没 `resume` 就 `add`，等于蒙着眼往别人刚写的地方盖字。
2. **一条线一个会话**。两个会话同时改同一本分册，即使不会覆盖，也会互相打乱顺序和口径。
3. **改口不要新加一条**。用 `revise` 或 `--supersede`，旧的自动标失效，历史仍能查。直接再写一条新的，下个会话会同时看到两个互相矛盾的口径。

## 七、常见误区

- **别把细节抄进主卡**。分册里有路径就够，主卡只留指针。主卡的价值与长度反相关。
- **别建"什么都装"的分册**。一本管一条线，超过一屏就该再拆。
- **别在没核对的情况下续用超期卡**。过期地图比没有地图危险。
- **别把推测写成确认**。念一遍：这句话能指回一句用户原话或一份文件吗？指不回就 `--pending`。
- **别手改卡片文件**。要改就走 `revise`，手改会让事件流和失效链断掉。
