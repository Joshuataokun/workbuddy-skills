# Example — 隐私敏感搜索（避开 google 痕迹）

## 适用情形

- 调研医药、法律、敏感个人话题（不想让 Google 账户关联）
- 写隐私技术 blog / 给同事评估搜索痕迹
- 跨设备 / 跨地区想清新结果

## DuckDuckGo + Startpage + Qwant 三件套

DDG 是主入口，自带 No-track；Startpage 拿 Google 结果但代理脱敏；Qwant 欧盟 GDPR。

```bash
# 隐私搜索：默认三个引擎一起
python scripts/multi_search.py "家用 VPN 推荐 2026" \
    --engines duckduckgo,startpage,qwant \
    --top 8 --delay 1.2
```

## DDG Bangs 跳转 DuckDuckGo Bang 列表

DDG Bangs 是 DuckDuckGo 独有的快捷跳转：

```bash
# 搜 GitHub 项目 (Bang !gh)
python scripts/multi_search.py "!gh torchserve" --engines duckduckgo --top 6

# 搜 Stack Overflow 问题
python scripts/multi_search.py "!so python memory leak" --engines duckduckgo

# 搜 npm 包
python scripts/multi_search.py "!npm express" --engines duckduckgo

# 搜 Docker 镜像
python scripts/multi_search.py "!docker nginx" --engines duckduckgo

# 搜 Wikipedia
python scripts/multi_search.py "!w transformer architecture" --engines duckduckgo
```

⚠️ DDG Bangs URL：`https://duckduckgo.com/html/?q=!gh+torchserve`，Bang 在 `?q=` 之后用 `!` 前缀，关键词用 `+` 分隔。

## 浏览器隐身模式 + 多引擎组合

隐私场景下，**强烈建议同时开 Brave Search + DDG + Startpage**：

```bash
python scripts/multi_search.py "GPT-4 jailbreak 2026" \
    --engines duckduckgo,startpage,brave,qwant --top 6
```

## 注意事项

- DDG HTML 版（`html.duckduckgo.com/html`）不需要 JS，更不会被 DDG 的 JS 检测拦截
- Startpage 自带"匿名查看"代理 — 点击结果时 IP 不暴露给目标站点
- Brave Search 独立索引（非 Google/Bing），被限较少
- Qwant 在欧盟服务器，受 CN 网络环境影响可能慢

## LLM 使用建议

> "调研某开源 LLM 框架的近一年安全公告，希望不留下任何 Google 痕迹。用 DDG + Startpage 跑 { 框架名 + security advisory 2026 }、{ 框架名 + CVE }、{ 框架名 + vulnerability report } 三组，结果给我列表即可——不要主动点击外链，让用户自己决策。"

LLM 应：
1. 选择 duckduckgo,startpage,brave 三个引擎
2. 跑三条 query
3. 输出 URL + 摘要 + 时间，但**禁止自动 web_fetch 跳转目标**
4. 在 SKILL.md 的隐私段提到这一点
