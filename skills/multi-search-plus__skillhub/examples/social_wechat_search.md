# Example — 微信公众号文章发现

> 搜狗微信搜索是唯一公开可触达微信公众号文章的入口。

## 适用情形

- 公众号行业调研（找特定行业头部账号 + 近期文章）
- 内容创作参考（找选题灵感、看同行写啥）
- 行业数据/报告/官方政策在公众号首发时的发现

## 触发方式

```bash
# 基本：搜最近微信公众号文章
python scripts/multi_search.py "跨境电商 选品" --engines sogou_wechat --top 8 --delay 1.5
```

期望看到形如：

```
1. **[2026年跨境电商选品趋势: 这5个品类最热](https://wx.sogou.com/link?url=...)**
   跨境电商红利期已过，进入精细化运营阶段。本文从平台数据…
   _source: sogou_wechat_
```

⚠️ 注意：微信返回的 URL 都是 `wx.sogou.com/link?url=...`，**点击会先经搜狗中转**—— 这是反爬策略，但实际可以打开看到原文章（除非原文已被删）。

## 搜特定公众号

```bash
# 搜特定公众号 (公众号:机器之心)
python scripts/multi_search.py "机器之心" --engines sogou_wechat

# 搜某公众号 + 主题交叉
python scripts/multi_search.py "远读 选品" --engines sogou_wechat --top 8
```

## 用 site: 把范围限定到公众号域

搜狗对 site 限定不太支持，但有变通——搜"公众号:xxx + 关键词"。

## 拿到正文

`wx.sogou.com/link?url=...` 是中转链接。要拿原文：

1. 复制 URL 到浏览器打开
2. 把这条 URL 喂给 web_fetch，让 LLM 直接抓正文：

```javascript
web_fetch({"url": "https://wx.sogou.com/link?url=ENCRYPTED_URL&type=2&query=关键词"})
```

⚠️ 微信文章 HTML 里很多是 <p> 段，LLM 抓回来后推荐用 `Markdown` 风格阅读，删除 `<p>` 干扰。

## 限制

| 限制 | 说明 | 应对 |
|------|------|------|
| 显示片段截断 | 搜狗只展示前 ~120 字的摘要 | 拿到 URL 再 web_fetch 抓全文 |
| 不显示阅读量 | 公众号搜索结果不含阅读量数据 | 需要另选「新榜」「西瓜数据」等 |
| 热搜词过滤 | 涉及敏感词搜不到 | 切换不同关键词组合 |

## LLM 一句话使用建议

> "用 sogou_wechat 搜「XXX」，列出前 10 条公众号文章，**同时标注文章对应的公众号名 + 发布日期**（LLM 自己尝试推断），把 URL 也列上。"

LLM 会自己用 web_fetch 单调搜狗微信搜索结果页面，再去重 / 摘要。
