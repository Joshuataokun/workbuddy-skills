# Example — 跨境电商选品价格对比

> 真实业务场景：在多个平台同时搜同一商品，横向比价 / 比口碑。

## 适用情形

- 跨境电商选品调研
- 多平台同步监控（淘宝、京东、1688、亚马逊、eBay）
- 找最便宜的同款 / 同款最低价

## 用 search operator 限定平台

```bash
# 淘宝
python scripts/multi_search.py "site:taobao.com 无线蓝牙耳机 工厂店" -e bing_cn

# 京东
python scripts/multi_search.py "site:jd.com 无线蓝牙耳机 自营" -e bing_cn

# 1688（拿货源价）
python scripts/multi_search.py "site:1688.com 无线蓝牙耳机 一件代发" -e bing_cn

# 亚马逊
python scripts/multi_search.py "site:amazon.com wireless earbuds under 30" -e google_hk

# eBay
python scripts/multi_search.py "site:ebay.com wireless earbuds" -e google_hk
```

## 批量调研（同一品类 × 多个平台）

把每个平台的查询写入 `queries.txt`：

```text
# 无线蓝牙耳机跨境选品
site:taobao.com 无线蓝牙耳机 工厂店
site:jd.com 无线蓝牙耳机 自营
site:1688.com 无线蓝牙耳机 一件代发
site:amazon.com wireless earbuds bluetooth 5.3
site:ebay.com wireless earbuds new
```

一条命令批量跑：

```bash
python scripts/batch_search.py --file queries.txt \
    --engines bing_cn,google_hk \
    --top 4 \
    --delay 1.5 \
    --json price-survey.json
```

输出 `price-survey.json` 含全部 query × 全平台结果，按 query 分段；可作为下一步分析（去重 / 排序 / Excel）的输入。

## 跨语种比价

```bash
# 同款产品：英文关键词
python scripts/multi_search.py "airpods pro 2 review reddit" -e google_hk --top 6

# 中文关键词
python scripts/multi_search.py "airpods pro 2 评测 知乎" -e bing_cn --top 6

# 隐私搜索（避开广告重定向）
python scripts/multi_search.py "airpods pro 2 cheapest price" -e duckduckgo,startpage --top 5
```

## 速率控制

跨境调研并发不要打高，避免 IP 被限。推荐参数：

| 参数 | 取值 | 理由 |
|------|------|------|
| `--max-workers` | `2` | 同时打两个引擎足矣，太快触发反爬 |
| `--delay` | `1.5`–`2.0` | 隔 1.5s 一次，跨平台也不至于被反爬 |
| `--top` | `4`–`6` | 选品阶段够用，太多反而稀释信噪比 |

## 常见误区

- ❌ **直接搜 "蓝牙耳机 推荐"**：搜到 90% 是软文，请用 `site:` + 限定品类型号
- ❌ **搜 1688 想直接看到底价**：1688 详情页要登录，搜出来基本只是标题页
- ❌ **同一秒内用 8 个引擎打**：立刻被 IP 限流
- ✅ **建议**: 选 2-3 个引擎 × 1.5s 间隔 × 5 条 top，3 分钟跑 30 条结果，比直接甩 100 条干净得多
