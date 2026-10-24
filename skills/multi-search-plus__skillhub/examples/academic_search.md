# Example — 学术研究（Google Scholar 替代 + WolframAlpha）

## 适用情形

- 学术综述、文献调研
- 数值计算 / 公式求解
- 不需要 Serper / Tavily 等付费 API

## 文献调研：Google Scholar + DuckDuckGo

Google Scholar 没有专门的 site 字段，但 duckduckgo + site: 能近似替代：

```bash
# Google Scholar (注意：Scholar 域名不同)
python scripts/multi_search.py "deep learning optimization survey 2024" \
    --engines google,google_hk --top 10

# DuckDuckGo 学术限定（接近 site:scholar）
python scripts/multi_search.py "deep learning optimization survey site:arxiv.org" \
    --engines duckduckgo --top 10

# 时间筛选（过去 1 年内的深度学习综述）
python scripts/multi_search.py "deep learning survey" \
    --engines google_hk --time year --top 8
```

## 学术 PDF 聚合

```bash
# 找 PDF 文件（Google filetype:pdf 操作符）
python scripts/multi_search.py "transformer architecture filetype:pdf" \
    --engines google_hk --top 8

# site:arxiv.org + filetype:pdf
python scripts/multi_search.py "site:arxiv.org LLM survey filetype:pdf" \
    --engines duckduckgo,startpage --top 8
```

## 数值计算：WolframAlpha

```bash
# 解方程
python scripts/multi_search.py "solve x^2-5x+6=0" --engines wolframalpha --top 4

# 积分
python scripts/multi_search.py "integrate sin(x) from 0 to pi" --engines wolframalpha

# 实时汇率
python scripts/multi_search.py "100 USD to CNY" --engines wolframalpha

# 物理常数
python scripts/multi_search.py "speed of light" --engines wolframalpha

# 化学计算
python scripts/multi_search.py "molar mass H2SO4" --engines wolframalpha
```

⚠️ WolframAlpha 是 JS 渲染页，本工具只能抓到 query + section 名进 Result；要拿数值答案，**直接复制 URL 到浏览器** 或用 LLM `web_fetch` 抓。

## 多源学术搜索（推荐写法）

综合 Google Scholar + arXiv + ResearchGate：

```bash
python scripts/batch_search.py --inline \
    "transformer architecture filetype:pdf" \
    "site:arxiv.org LLM survey 2024" \
    "site:researchgate.net knowledge graph 2025" \
    --engines google_hk,duckduckgo,startpage \
    --top 5
```

## LLM 使用建议

> "调研「LLM Agent」领域的近 18 个月关键论文，用 `python scripts/batch_search.py` 跑 { site:arxiv.org LLM Agent }、{ site:openreview.net LLM Agent }、{ LLM Agent survey filetype:pdf } 三组 query，把结果写到 research-notes.md 留给我。"

LLM 应该：
1. 自己组装 queries.txt
2. 跑 batch_search.py，输出 markdown
3. 拿到 URL 列表后再批量 web_fetch 摘要
4. 输出"研究笔记"前给出 5 个明确的"核心观察 / 数据点 / 趋势"作为前置摘要
