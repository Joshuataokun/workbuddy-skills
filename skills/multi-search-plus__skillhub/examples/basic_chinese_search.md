# Examples — basic Chinese multi-engine search

> 最常见场景：中文关键词，触发所有国内引擎。

## 适用情形

- 用一句中文描述问题，想要多角度网页结果做横向参考
- 默认只用国内 8 个引擎（百度 + 必应中国/国际 + 360 + 搜狗 + 微信 + 头条 + 神马）
- 期望 5-10 秒内拿到去重结果，不依赖任何 API Key

## 触发方式 A：CLI 脚本（推荐）

```bash
python scripts/multi_search.py "大模型微调 教程" \
    --engines cn \
    --top 5 \
    --delay 1.2
```

期望（真实抓取，去重）：

```
# Multi-Engine Search Results
**Query**: 大模型微调 教程
**Engines**: 8 (succeeded=N)   # 多数成功，Baidu/微信被反爬时 others 仍可用
**Elapsed**: 6–8s
**Total unique results**: 8–15
```

每条结果形如：

```
1. **[runoob.com Python 微调指南](https://www.runoob.com/python-tutorial.html)**
   提供从零开始的大模型微调示例代码……
   _source: bing_cn_
```

## 触发方式 B：LLM 在线调用 web_fetch

LLM 不会因为没装 scripts 就停摆——它会按 SKILL.md 提示调 `web_fetch` 抓单条 URL：

```javascript
// 百度
web_fetch({"url": "https://www.baidu.com/s?wd=大模型微调 教程"})
// 必应
web_fetch({"url": "https://cn.bing.com/search?q=大模型微调 教程&ensearch=0"})
// 微信公众号（重磅，因为公众号内容只有搜狗微信能搜）
web_fetch({"url": "https://wx.sogou.com/weixin?type=2&query=大模型微调"})
// 知乎（用 site: + 搜狗）
web_fetch({"url": "https://www.sogou.com/web?query=site:zhihu.com+大模型微调"})
```

LLM 在多次 web_fetch 后，应自行去重 / 摘要，并标注每条结果的来源。

## 进阶：用站点 + 时间筛选

```bash
python scripts/multi_search.py "site:github.com 大模型微调" --engines bing_cn,google_hk --top 5

python scripts/multi_search.py "Rust 1.80 新特性" --engines google_hk --time week --top 5
```

## 注意事项

- **Baidu 的反爬**：高频请求会得到 "百度安全验证" 占位页；脚本会自动跳过结构化结果，但在 `Per-Engine Status` 里看到 `baidu OK 0 results` 时不要惊讶。
- **Bing CN vs Bing INT**：走同一服务器但 `ensearch=0/1` 切换中文/英文结果。两条独立调度，去重时仍然会合并。
- **微信**：搜狗微信搜索只返回公众号文章片段 + 跳转链接；要拿全文需要再 web_fetch 跳转目标。
