# 调研沉淀：集中存放的存与取完整流程

本文件是 `research-vault` 1.1.0 的详细操作手册。所有资料库读写通过系统内置 `library` 技能完成——本文件给出命令与约定，遇到报错、节点不存在、权限问题，以 `library` 技能的 `error_handling.md` 为准，不臆造 API。

## 0. 目录结构总根与项目文件夹

```
调研沉淀/                          ← 总根 folder（唯一）
└── <项目名>/                      ← 一个项目空间一个文件夹
    ├── 00-索引.md                 ← doc，快速召回入口
    ├── 结论/                      ← folder，四栏结论卡片
    ├── 来源/                      ← folder，剪藏的 link 节点
    └── 待核实/                    ← folder，失败剪藏 / 无来源结论
```

### 0.1 项目名怎么取（关键）

1. 读 `~/.workbuddy/workspace-display-names.json`（**只读，绝不改写**）。
2. 用当前工作区绝对路径（小写、正斜杠）匹配 `workspaces` 里的 key，取 `displayName`。
3. 没有匹配记录 → 用空间目录名（basename），如 `E:/WorkBuddy/学习无名` → `学习无名`。
4. 用户当轮明确指定了项目名 → 以用户说的为准。

记下项目名，本轮后续所有节点都落到 `调研沉淀/<项目名>/` 下。

### 0.2 确保目录齐全（幂等，不重复建）

按层级逐级检查，缺哪级建哪级：

```bash
LIB="<library 技能根目录>"
WS="AhxKIqmP7I9lPVk8AL3IZs"     # 个人空间 spaceId；以 list-user-spaces 实测为准

# 找总根：list-nodes 看空间根有没有标题「调研沉淀」的 folder
python3 "$LIB/space_api.py" space.workspace.list-nodes --space-id "$WS" --limit 100
# 没有 → 建
python3 "$LIB/manage/create_folder.py" --title "调研沉淀" --space-id "$WS"

# 项目文件夹：在总根下找/建
python3 "$LIB/manage/create_folder.py" --title "<项目名>" --space-id "$WS" --parent-id "<总根 nodeId>"

# 三个子文件夹：在项目文件夹下找/建
python3 "$LIB/manage/create_folder.py" --title "结论" --space-id "$WS" --parent-id "<项目 nodeId>"
python3 "$LIB/manage/create_folder.py" --title "来源" --space-id "$WS" --parent-id "<项目 nodeId>"
python3 "$LIB/manage/create_folder.py" --title "待核实" --space-id "$WS" --parent-id "<项目 nodeId>"
```

先列后建、同名复用（含空文件夹），绝不重复建同名。建完把各级 `nodeId` 记在手边，后面都用 id 定位。

## 1. 存（capture）

### 1.1 拆分原始资料 vs 结论

| 类型 | 例子 | 去处 |
|---|---|---|
| 原始来源页 | 官方文档、GitHub README/issue、技术博客 | 剪藏 →「来源/」 |
| 可复用判断 | 选型结论、踩过的坑、被否方案、关键数字+出处 | 结论卡片 →「结论/」 |
| 没抓到 / 无来源 | 剪藏失败、只有推断没有出处 | →「待核实/」 |

原始正文交给剪藏节点，结论卡片只放判断。

### 1.2 剪藏网页并归位（1.1.0 关键修复）

`doc.create-link` 只接受 `--url` 和 `--title`，**没有 `--parent-id`**——新建的 link 会落在库根目录。所以建完必须立刻移动归位：

```bash
# 1) 剪藏（落在默认位置）
python3 "$LIB/space_api.py" doc.create-link --url "<url>" --title "<标题>"
# 取返回的 data.nodeBlockId

# 2) 立刻归位到项目「来源/」
python3 "$LIB/space_api.py" space.workspace.move-node \
  --node-id "<link 的 nodeBlockId>" --target-parent-id "<来源 folder nodeId>"
```

- 抓取异步：`doc.get-link-content --node-id <id>` 查 `data.status`，`pending` 隔约 3 秒再查，累计 5 分钟仍 pending → 把 link 移到「待核实/」并说明正文抓取中。
- `failed` → 移到「待核实/」，并把 URL 原样写进结论卡片来源栏，不静默丢弃。
- GitHub 仓库没有可抓正文时，把仓库地址剪藏，或在结论卡片来源栏写清 `仓库名 + 关键文件路径 + commit/日期`。

**铁律：任何情况下都不许让剪藏出来的 link 留在库根目录。**

### 1.3 结论卡片（doc 节点）

一个主题一份 doc，标题**不带**"调研沉淀 /"前缀（文件夹已经是项目上下文）：

```
<主题> 调研结论（YYYY-MM-DD）
```

正文纯 Markdown，每条结论四栏：

```markdown
# <主题> 调研结论（YYYY-MM-DD）

## 结论 1：<一句话判断>
- 结论：<可复用的判断，数字/选型/事实，带单位和出处>
- 依据：<证据或推理链>
- 被否方案：<没采用的方案及原因；没有就写"无"，不许省这一栏>
- 来源：<URL 或剪藏节点链接；没来源标 [待核实]>

## 结论 2：<一句话判断>
- 结论：
- 依据：
- 被否方案：
- 来源：

## 待确认 / 未解
- <还没查清的点>
```

字段规则：

- **结论**：能脱离上下文单独读懂的判断句，不写"这个/上述"这类指代。
- **依据**：让下次的自己信得过的证据或推理链。
- **被否方案**：最关键——写下"为什么不选另一条路"，否则几轮后会把已推翻方案重新捡起。没有就写"无"。
- **来源**：可点击 URL 或剪藏节点链接。无来源标 `[待核实]` 并进「待核实/」，不算完整沉淀。
- 多条独立结论 → 多个"结论 N"小节。
- 表格用 GFM `|---|`，代码/图示用三反引号 fenced code，不混 WorkBuddy 组件标签。

建文档（`--content-file` 传正文，不内联进 shell 字符串）：

```bash
python3 "$LIB/doc/create_doc.py" --title "<主题> 调研结论（<日期>）" \
  --space-id "$WS" --parent-id "<结论 folder nodeId>" --content-file "<临时 md 路径>"
```

- 复杂正文先 `--dry-run`；含 GFM 表格可直接建。
- 返回 `KS_USER_REPLY` 原样转给用户。
- `failedCount`/`fatalCount` > 0 → 提醒用户打开核对。
- 超时 → 别盲目重试，先读回节点确认是否空壳再决定覆盖/补写。

### 1.4 更新 00-索引.md（快速召回的关键）

每次存完必须更新项目索引。索引是**一份短文档**，不是全文副本：

```markdown
# <项目名> 调研索引

> 本文件夹收录该项目的联网/GitHub 调研。召回时先读本索引，按标题定位卡片。

## 结论卡片
| 主题 | 一句话 | 来源数 | 更新 | 链接 |
|---|---|---|---|---|
| 开源方案与选型 | 走方案A自研，否决换底座/现成成品 | 9 | 2026-11-18 | /space/d/xxx |
| 数据真值与反汇编纠偏 | ... | 3 | 2026-11-18 | /space/d/xxx |

## 来源剪藏
- <URL 或节点标题> — 收录日期

## 已推翻 / 过时
- <旧结论> → 被 <新结论/日期> 替代
```

- 用 `get_doc_reviews.py` 读回现有索引再改（不拿旧内容当新内容）；新建用 `create_doc.py` 建到项目根（不是「结论/」子目录）。
- 索引保持短——卡片多了只加一行，不堆正文。

### 1.5 存完收尾

给用户一句确认：存了几条链接、哪份结论卡片、索引已更新，附链接。不在对话里复述全文（那会重新堆满窗口）。

## 2. 取（recall）

用户问"之前调研过 X 吗"：

1. **定项目**：按当前工作区 displayName 确定项目文件夹；用户说的是别的项目就切到那个文件夹。
2. **锁范围检索**：用 `library_search`，`targets` 锁到该项目文件夹 nodeId（不是全库）：

```json
{"query": "关于 X 的调研结论和被否方案", "targets": [{"type": "node", "id": "<项目 folder id>"}]}
```

3. **先读索引**：`get_doc_reviews.py` 读 `00-索引.md`，先扫标题级清单定位。
4. **组织输出**：按"结论 + 依据 + 来源"列出，关键判断标 `[N]`，末尾按首次出现顺序列来源节点。
5. **标过时**：同一主题多份卡片时新的优先，明确指出"某结论已被某次调研更新/推翻"。
6. **要全文再读**：按命中节点 `nodeKind` 走对应入口读回（doc → `get_doc_reviews.py`，link → `doc.get-link-content`），不用片段当全文。
7. **没命中**：直说「该项目的调研沉淀里没找到相关记录」，可补通用知识但标明"这不是库里的"。**绝不把模型记忆伪装成库里的结论**。

## 3. 话术模板（可复制）

存：

```
把这次调研存进资料库：按当前项目建/用项目文件夹，网页剪藏归位到「来源/」，
结论按"结论/依据/被否方案/来源"四栏写到「结论/」，最后更新 00-索引.md。
```

取：

```
查资料库「调研沉淀」下 [项目名] 文件夹里关于 [主题] 的结论，
先读 00-索引，再按"结论 + 依据 + 来源"列出来，标出过时的，没找到就直说。
```

## 4. 异常处理

- 资料库未授权 / 检索报错 → 按 `library` 技能错误处理走，用自然语言告诉用户，不暴露内部码。
- 节点 id 从链接解析后先 `node-info` 确认类型再操作，别凭链接猜标题或类型。
- move-node 目标是另一个空间时要 `--target-space-id`；本项目内移动不需要。
- 只碰用户明确给出的路径与资料库内容，不自行扫描本地目录。
