# Anti-Patterns — multi-search-plus v2.2.0

> 一份「**这 10 件事别做**」的清单。所有条目都来自真实失败案例，遵循能省你 30 分钟。

## 1. ❌ 把这个 Skill 当万能 API 用

**失败案例**：让 LLM "搜索 1000 条数据并保存"。

**为什么失败**：
- 17 个引擎**都没有公开 API**，全部走 HTML 抓取
- 单 IP 高频请求 = 被反爬熔断
- 没有 SLA、没有稳定性承诺、可能随时调整页面结构

**正确做法**：
- 选品 / 调研：单次 8-15 条足矣
- 真要 1000+ 条数据 → 用 Serper/Tavily/Exa 付费 API 替代（见 `web-search-plus` 类 skill）
- 或者用 `sites:` 限定平台后做针对性抓取 + RSS / sitemap

## 2. ❌ 把 `--max-workers` 调到 10+

**失败案例**：脚本启动后 30 秒内全引擎失败。

**为什么失败**：
- 单 IP 同时打 10+ 引擎，几乎一定触发反爬熔断
- 网络层：`connection reset` / 429 / 403
- 应用层：每个引擎都返回 "访问频繁，请稍后再试"

**正确做法**：
- 默认 `--max-workers 3`（同时打 3 个）
- 跨境电商等敏感场景 → `--max-workers 2 --delay 2.0`
- 调试 / 自检 → `--max-workers 1` 顺序跑

## 3. ❌ 把搜狗微信结果直接当成文章 URL

**失败案例**：把 `wx.sogou.com/link?url=...` 当原文链接发给用户。

**为什么失败**：
- 这是搜狗的**中转 URL**，包含加密跳转 + 防爬参数
- 用户点开确实能看到原文（多数情况），但 LLM 把它当真 URL 就错了

**正确做法**：
- LLM 拿到这个 URL 后，自己 web_fetch 一次让搜狗跳转过去
- 或者**明确告诉用户**："这是搜狗中转 URL，点击会跳转"
- 不要在对外输出里把 `wx.sogou.com/link?url=...` 当成"原文链接"

## 4. ❌ 期望所有 17 引擎都返回结果

**失败案例**：脚本跑完后 0 results，用户以为坏了。

**为什么失败**：
- 国内网络环境下，Google / Brave / DuckDuckGo 经常 timeout
- Baidu 高频请求会触发反爬验证页（status=200 但内容是验证图）
- 一个引擎失败**不影响其他引擎**——这是设计如此

**正确做法**：
- 看 `Per-Engine Status` 部分：`OK` 数 = 实际跑通的引擎数
- 0 unique results 时，先用 `setup_check.py` 看网络环境
- 默认参数下，应该至少有 3-6 个引擎成功

## 5. ❌ 把它当万能爬虫，每天 24 小时跑

**失败案例**：把脚本塞进 cron 每 5 分钟跑一次，3 天后 IP 被百度拉黑。

**为什么失败**：
- 没有 ToS 合规机制——脚本对 ToS 的态度是"用户自负责任"
- 各搜索引擎对自动化抓取有显式或隐式限制
- 长期高频使用 = 法律灰区

**正确做法**：
- 单次会话最多跑 50 个 query，之后暂停 30 分钟
- 做监控类应用 → 缓存结果，用 RSS / sitemap 替代
- 生产环境 → 用付费 API（Serper / Tavily），费用可控

## 6. ❌ 把 `--time week` 用在非 Google 引擎上

**失败案例**：传 `--time year` 但用 bing_cn，发现没生效。

**为什么失败**：
- `--time` 只对 `google` 和 `google_hk` 生效（用 `tbs=qdr:` 参数）
- 其他引擎时间筛选参数不同：Bing 用 `qft=`、Baidu 用 `gpc=`、DDG 用 `df=`

**正确做法**：
- 想用时间筛选 → `--engines google_hk` 配 `--time week`
- 或者直接用搜狗引擎，它本身默认按时间倒序
- 或者不用 `--time`，让 LLM 在 query 后面手动加 `last week` 关键词

## 7. ❌ 在 query 里加 `inurl:` / `cache:` 后期待所有引擎支持

**失败案例**：搜 `inurl:admin login`，Bing 给出 0 结果。

**为什么失败**：
- `inurl:`、`intitle:`、`cache:`、`related:` 是 Google 专属操作符
- Bing 仅支持部分（`site:`、`filetype:`、`contains:`）
- Baidu 仅支持 `site:`、`intitle:`、`inurl:`

**正确做法**：
- 想跨引擎 → 只用 `site:`、`filetype:`、`""`、`-`、`OR`
- 想用 `cache:` / `related:` → 只跑 google / google_hk
- 想限定 URL 路径 → `site:` + 限定站点，更可靠

## 8. ❌ 不看 Per-Engine Status 就下结论

**失败案例**：脚本输出 0 results，LLM 直接告诉用户"搜索失败"。

**为什么失败**：
- 0 unique results ≠ 全部失败
- 可能是 Baidu 1 个成功但 0 results（HTML 被反爬），其他 7 个因为 IP 限流全失败
- 也可能是 query 太特殊（无任何结果）

**正确做法**：
- LLM 必须**先看 Per-Engine Status**，判定哪个层级失败
- 如果所有引擎 HTTP OK 但 0 results → 调整 query
- 如果多个引擎 timeout → 等几分钟再跑（或换网络环境）
- 如果 1-2 个引擎 timeout 其他成功 → 正常，去掉 timeout 的引擎即可

## 9. ❌ 用脚本当 LLM 的唯一搜索入口

**失败案例**：LLM 调 `subprocess.run(["python", "scripts/multi_search.py", query])`，但 LLM 自己都没装 Python。

**为什么失败**：
- scripts/ 是**离线批量场景的强化**，不是唯一入口
- LLM 在线对话时，应该直接用 `web_fetch` 调单条 URL
- 脚本更适合用户自己跑、自动化任务、批量调研

**正确做法**：
- LLM 在线对话 → 用 SKILL.md 里 Quick Examples 的 `web_fetch` 调用
- 用户/自动化 → 用 `python scripts/multi_search.py`
- 混合场景：LLM 建议"你可以跑 `python scripts/multi_search.py ...`"

## 10. ❌ 把搜狗微信 / 头条当成万能中文搜索

**失败案例**：搜 `python 入门` 走 sogou_wechat，结果全是公众号，丢失网页内容。

**为什么失败**：
- sogou_wechat 只搜公众号，**不返回网页结果**
- 头条搜的权重偏向字节系内容（抖音、西瓜）
- 神马搜偏移动端，**PC 网页质量较低**

**正确做法**：
- 综合中文搜索 → 默认 `cn`（8 个引擎一起）
- 想专门搜公众号 → 只跑 sogou_wechat
- 想专门搜知乎 → `sogou` + query 加 `site:zhihu.com`
- 想搜字节生态 → `toutiao`

---

## 速查决策表

| 场景 | 推荐引擎 | 反模式 |
|------|----------|--------|
| 综合中文搜索 | `cn` (8 引擎) | 只用 baidu（被反爬）|
| 微信公众号 | `sogou_wechat` | 用 `cn`（会拿到很多非公众号内容）|
| 隐私英文搜索 | `duckduckgo,startpage,brave` | 用 google（留痕迹）|
| 学术文献 | `google_hk,duckduckgo` + `site:arxiv.org` | 期望 google scholar 有 site 操作符 |
| 时间敏感新闻 | `google_hk --time day` | 用 bing_cn（无 tbs 参数）|
| 跨境电商调研 | `bing_cn,google_hk` + `site:` | 一次跑 8 引擎（被 IP 限流）|
| 知识计算 | `wolframalpha` | 期望搜网页结果（这是计算引擎）|