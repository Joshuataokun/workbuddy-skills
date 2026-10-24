---
name: multi-search-plus
description: "Aggregated search across 17 engines (8 CN + 9 global) with zero API keys. Includes a runnable Python aggregator (scripts/multi_search.py) for parallel fan-out, dedup, and JSON/Markdown output — LLM can also call web_fetch directly on each engine URL."
version: 2.2.0
---

# Multi Search Engine  (v2.2.0)

> 一个轻量、可执行、无 API Key 的多引擎聚合搜索工具。LLM 既可以**直接用 web_fetch 抓单引擎 URL**，也可以**调用 scripts/multi_search.py 做批量并行调度**——两条路径互不冲突，按场景选择。

---

## 0. 30 秒上手

```bash
# 必备：先跑一遍环境自检
python scripts/setup_check.py

# 立刻跑一次（CN 默认 8 引擎）
python scripts/multi_search.py "你的关键词"

# 限定引擎
python scripts/multi_search.py "跨境电商 选品" --engines bing_cn,google_hk

# 批量（从文件）
python scripts/batch_search.py --file queries.txt --md

# 输出 JSON 供后续处理
python scripts/multi_search.py "AI 教程" --json out.json
```

无需安装第三方依赖——纯 Python 3.8+ stdlib。

---

## 1. 何时触发本 Skill

| 信号 | 推荐动作 |
|------|----------|
| 主人说「搜一下」「查一下」「帮我找 XX 资料」 | ✅ 触发；按 query 自动选 CN / global / both |
| 主人说「对比这三个产品在 5 个平台的价格」 | ✅ 触发；推荐 `batch_search.py` |
| 主人说「搜 XX 的微信文章」 | ✅ 触发；只用 `sogou_wechat` |
| 主人说「解方程 / 汇率 / 化学式」 | ✅ 触发；走 `wolframalpha` |
| 主人说「用 Serper / Tavily API 搜」 | ❌ 别用本 Skill，引导到付费 API skill |
| 主人说「实时监控 XX 关键词每天变价」 | ⚠️ 不推荐；脚本无 SLA 承诺，超额会反爬 |

---

## 2. 决策树（Trigger Flow）

```
主人的搜索请求
    │
    ├── 关键词是中文？ ──yes──> 默认走 CN 8 引擎（baidu + bing + 360 + sogou + 微信 + 头条 + 神马）
    │                       │
    │                       └─ 提到「公众号」?──yes──> 仅 sogou_wechat
    │
    ├── 关键词是英文？ ──yes──> 默认走 global 9 引擎（google_hk + duckduckgo + brave + startpage + qwant + ...）
    │                       │
    │                       └─ 提到「隐私」?──yes──> 仅 duckduckgo,startpage,brave
    │
    ├── 数学/汇率/化学/股票 ──yes──> wolframalpha（仅 1 引擎，结果是 JS 渲染页）
    │
    └── 涉及大量 query 批量 ──yes──> scripts/batch_search.py
```

---

## 3. 引擎目录（17 个）

### Domestic (8) — 国内
- **baidu** — 中文索引最全，反爬敏感
- **bing_cn** — 必应中国版，中文结果首选
- **bing_int** — 必应国际版，英文结果走中国服务器
- **so360** — 360 搜索，安全防护内置
- **sogou** — 搜狗网页，知乎优化好
- **sogou_wechat** — 微信公众号唯一公开入口
- **toutiao** — 头条搜索，整合字节系内容
- **shenma** — 神马移动搜索，UC 默认

### Global (9) — 国际
- **google** / **google_hk** — Google 主站 / HK，国内可达优先 HK
- **duckduckgo** — DDG HTML 版，无 JS 也能用
- **yahoo** — Yahoo 国际搜索
- **startpage** — Google 结果 + 隐私保护
- **brave** — 独立索引（不依赖 Google/Bing）
- **ecosia** — 环保搜索
- **qwant** — 欧盟 GDPR 合规
- **wolframalpha** — 知识计算/数据查询（非网页搜索）

完整 URL 模板与高级操作符见 `references/advanced-search.md`（国内）和 `references/international-search.md`（国际）。

---

## 4. 三条调用路径（按场景选）

### 路径 A — LLM 在线对话：`web_fetch` 单条调用（最常用）

LLM 在对话中直接调：

```javascript
web_fetch({"url": "https://cn.bing.com/search?q=跨境电商 选品&ensearch=0"})
web_fetch({"url": "https://wx.sogou.com/weixin?type=2&query=跨境电商"})
```

**适合**：单次调研、对话中即时展示、LLM 自取摘要。LLM 应**自行去重** + **标注来源**。

### 路径 B — 脚本批量：`scripts/multi_search.py`

```bash
python scripts/multi_search.py "site:github.com react 教程" \
    --engines bing_cn,google_hk \
    --top 8 --delay 1.5 --json out.json
```

**适合**：调研阶段要 10+ 条结果、跨引擎横向对比、输出 JSON 给后续分析。

**特性**：
- 并发调度（默认 3 worker）+ 1.5s 间隔
- 自动去重（基于 URL 规范化 + 去 utm_* 跟踪参数）
- 引擎失败自动降级——单引擎 4xx/5xx 不影响其他
- JSON / Markdown / TSV 三种输出格式

### 路径 C — 批量多 query：`scripts/batch_search.py`

```bash
python scripts/batch_search.py --inline "Q1" "Q2" "Q3" \
    --engines cn --top 4 --json batch.json
```

**适合**：选品调研的"5 个平台 × N 个品类"、新闻订阅汇总、跨域对比。

---

## 5. 关键能力一览

| 能力 | 命令示例 |
|------|----------|
| 单引擎搜索 | `--engines baidu` |
| 时间筛选（仅 Google）| `--time week` |
| 文件型限定 | `query = "机器学习 filetype:pdf"` |
| 站内搜索 | `query = "site:github.com react"` |
| 排除词 | `query = "python -snake"` |
| 精确匹配 | `query = '"machine learning"'` |
| 或运算 | `query = "cat OR dog"` |
| DDG Bangs 跳转 | `query = "!gh tensorflow"` |
| 并发上限 | `--max-workers 3` |
| 单引擎间隔 | `--delay 1.5` |
| 输出格式 | `--md` / `--json` / `--tsv` / 默认 human |

更多操作符（Google/Bing 高级语法）见 `references/` 两个文档。

---

## 6. 限制 / 已知短板

1. **反爬熔断**：高频请求会被百度/微信/Google 触发限流；默认参数是经过实测的"安全值"
2. **无 SLA**：脚本对引擎服务稳定性不做承诺，HTML 改版可能导致解析失败
3. **WolframAlpha 结果抓不全**：该引擎结果靠 JS 渲染，本工具只能抓到 query + section 名
4. **国际引擎在国内可达性差**：Google/Brave/DDG 在国内网络环境下经常 timeout
5. **Bing CN/INT 重叠**：两套走同一服务器，结果经常重复（dedup 会处理）
6. **解析器正则**：HTML 结构改版时解析器可能漏抓，回归 `setup_check.py`

详细限制与应对见 `knowledge-base/rate-limits.md`；反模式清单见 `references/anti-patterns.md`。

---

## 7. 安全与隐私声明

- ✅ **零 Cookie 持久化**：所有 Cookie 仅在内存中存活，搜索会话结束自动清理
- ✅ **零 API Key**：仅用公开搜索 URL，不采集任何身份凭证
- ✅ **零配置文件泄露**：不读写任何 user-data 文件
- ✅ **零数据外传**：所有结果只在本地 stdout / 用户指定路径输出
- ⚠️ **ToS 自负**：使用本工具即代表用户已知搜索引擎 ToS 限制，自负责任
- ⚠️ **速率限制**：高频使用可能触发 IP 封禁，请遵守 `knowledge-base/rate-limits.md`
- ⚠️ **隐私引擎推荐**：真要隐私搜索只用 `duckduckgo,startpage,brave` 三件套，不要混入 Google

---

## 8. 文件结构

```
multi-search-plus/
├── SKILL.md                       ← 你正在看
├── README.md                      ← 给用户看的快速了解（可选）
├── metadata.json                  ← 平台元数据
├── config.json                    ← 引擎 URL 配置
├── CHANGELOG.md                   ← 版本历史
├── scripts/
│   ├── multi_search.py            ← 核心并行调度器（stdlib only）
│   ├── setup_check.py             ← 环境预检（13 项检查）
│   └── batch_search.py            ← 批量查询 runner
├── examples/
│   ├── basic_chinese_search.md
│   ├── ecommerce_price_compare.md
│   ├── social_wechat_search.md
│   ├── academic_search.md
│   └── privacy_search_demo.md
├── references/
│   ├── advanced-search.md         ← 国内引擎高级搜索指南
│   ├── international-search.md    ← 国际引擎高级搜索指南
│   └── anti-patterns.md           ← 10 条反模式清单
└── knowledge-base/
    └── rate-limits.md             ← 速率限制与失败应对
```

---

## 9. 相关 Skill

- `web-search-plus` — 用 Serper / Tavily / Exa 付费 API，主打英文研究
- `brave-search` — 单 Brave 引擎，强调独立索引
- `SearXNG-Skill` — 自托管元搜索

本 Skill 优势：**零 API Key + 中文友好 + 真正可执行的 Python 脚本**——是 SkillHub 上少有的"下载就能用"的多搜索工具。

---

## 10. License

MIT