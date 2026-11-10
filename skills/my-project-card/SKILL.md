---
name: my-project-card
display_name: 我的项目卡片
display_name_en: My Project Card
description: 项目空间卡片（用户口语：空间卡片、技能卡片、项目卡、状态板）。一个工作空间或一个长期项目建一张卡，记目标、口径、已排除方案、进度、待办和踩过的坑；每条工作线一本分册，多个会话同时干活不会互相覆盖。用户说"更新空间技能卡片""更新空间卡片""更新卡片""卡里记一下""记到卡片""读卡""接着上次""上次做到哪了""继续上次的活""这个空间干到哪了""开个分册"时使用。这是往项目卡里写记录，不是修改技能文件，也不是空间收敛。
description_zh: 项目空间卡片（用户口语：空间卡片、技能卡片、项目卡、状态板）。一个工作空间或一个长期项目建一张卡，记目标、口径、已排除方案、进度、待办和踩过的坑；每条工作线一本分册，多个会话同时干活不会互相覆盖。用户说"更新空间技能卡片""更新空间卡片""更新卡片""卡里记一下""记到卡片""读卡""接着上次""上次做到哪了""继续上次的活""这个空间干到哪了""开个分册"时使用。这是往项目卡里写记录，不是修改技能文件，也不是空间收敛。
description_en: Project-space card for one workspace or one long-running project - goal, constraints, rejected approaches, progress, todo and pitfalls, with one sub-card per workstream so concurrent sessions never overwrite each other. Use when the user says update the space skill card, update the space card, update the card, note it on the card, read the card, continue from last time, where did we leave off, or create a sub-card. This writes records into the project card; it does not modify skill files.
version: 2.1.1
author: Joshuataokun
tags: 项目卡片,空间卡片,技能卡片,项目卡,状态板,主卡,分册,接着上次,跨会话,多会话,进度延续,工作面,踩过的坑
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
~/.workbuddy/cards/.stop-guard.log      守卫判定日志（不属于任何一张卡）
~/.workbuddy/cards/.stop-guard-off      守卫总开关，文件存在即停用
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

# 查漏：谁读过卡却没写卡 / Stop 守卫拦了几次、有没有补上
python $CARD audit
python $CARD audit --slug poker-game
```

`add` 一条命令内部依次完成：锁 → 查重 → 备份 → 写入 → 更新事件流 → 刷简报 → 打印计数。**不需要读任何报告文件。**

改了这个技能的引擎代码，跑一遍 `python scripts/acceptance.py`（含八进程并发写同一分册、Stop 守卫放行/拦截回归）。

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

0. 若当前工作区有 `.workbuddy/HANDOVER.md` 且 7 天内更新过 → **先读全文**。SessionStart 注入的只是 ≤220 字符摘要；HANDOVER 记的是「压缩瞬间做到哪 / 下一步 / 未决口头事项」，属于会话态，不是卡片里的长期状态。细则见 `workspace-converge/references/handoff-guide.md`。卡片里**不要重复**抄这些内容

1. `resume` 看三块：**简报顶部「⚠ 开工先读：坑与已排除方案」**（已从主卡和各分册自动抽取，涉及对应场景必须先遵守）、谁在动哪个工作面、待办与待确认；`resume` 会往事件流写一条 `open` 留痕，不改卡片内容；
2. 简报里显示某个工作面正被别人占着 → 先跟用户说一声，或换一条线；
3. 主卡超过 `--stale-days`（默认 14 天）没更新 → 先核对口径再干，不拿旧卡直接上手。

**收尾**（一次 `add` 一条，别攒）：

1. 做完了什么 → 主卡 `完成`，或对应分册 `已完成`
2. 用户新定的规矩 → 主卡 `口径`；只对某条线成立的进分册
3. 被否的方案、踩过的坑 → 主卡 `排除`（带原因）／分册 `坑`（带现象和解法）。**坑必须带触发场景**——什么情况下该想起它；无场景的坑下个会话接不上当前动作，等于没记
4. 冒出未决问题 → `--pending` 进 `待确认`
5. 走之前 `release`，让别的会话知道这条线空出来了

### 强制收尾（v2.1.0 起，不靠自觉）

`resume` 的 `open` 留痕让用户级 `Stop` 守卫知道「这个会话碰过卡片」。守卫**不依赖技能有没有被触发**：只要当前工作区有卡，每次助手答完都会检查，四个条件同时成立才拦一次收工，把补卡命令塞回对话：

1. 当前 `cwd` 能对应到一张已建的卡；
2. 本轮（最后一条用户消息之后）确实动了文件；
3. 本轮这张卡的事件流里没有 `add` / `revise` / `claim`；
4. 本轮还没被拦过（`stop_hook_active` 为 false）。

补完卡后第二次自动放行，最多多一轮，不会卡死。被提醒后仍没补卡的，记一条 `miss`，`audit` 能查出来。

- **查漏**：`python $CARD audit` → 谁读过卡没写、守卫拦了几次、提醒后仍未补卡几次。
- **停用**：在 `~/.workbuddy/cards/` 建一个空的 `.stop-guard-off` 文件，守卫立即静默放行；删掉即恢复。判定日志在 `~/.workbuddy/cards/.stop-guard.log`。
- **fail-open**：找不到卡、没有 transcript、切不出本轮边界、本轮纯只读、脚本自身出错，一律放行。守卫宁可漏拦，绝不把会话卡住。
- **生效前提**：hooks 是用户级全局配置，改完 `settings.json` **不会热加载**，要重启 WorkBuddy 或在 `/hooks` 面板审阅后才生效；本机 5 张卡、所有空间都会受影响。
- **收尾归属**：`workspace-converge/references/wrap-routing.md` 是主本——项目状态写卡片，长期口径写空间 `MEMORY.md`，过程写当天日志，中间产物由 Stop hook 的清理脚本处理。**同一件事只写一处**；助手不自己删文件。

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
- **别为应付守卫硬凑条目**。本轮真没产生需要留存的结论，说明理由收工即可；写套话比漏记更坏。
