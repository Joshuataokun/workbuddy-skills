# Rate Limits & Failure Recovery — multi-search-plus v2.2.0

> 何时会触发反爬 / 限流？降级链路是什么？

## 默认速率参数

| 参数 | 默认值 | 范围 | 何时调整 |
|------|--------|------|----------|
| `--max-workers` | `3` | `1`–`5` | 网络受限 → 降；宽带充裕 + 内网 → 升 |
| `--delay` | `1.5` | `0.5`–`3.0` | 短间隔 = 易反爬；长间隔 = 慢 |
| `--timeout` | `8.0s` | `3.0`–`15.0` | 网络慢 → 调长；服务器热启快 → 调短 |
| `--top` | `8` | `3`–`15` | 调研需要 top 5-6；监控扫描 top 12+ |

## 各引擎的反爬敏感度

| 引擎 | 敏感度 | 触发反爬阈值（估计） | 表现 | 恢复时间 |
|------|:------:|--------------------|------|----------|
| Baidu | ⚠️ 高 | 单 IP ~20 RPM | "百度安全验证" 占位页 | 数小时 |
| Bing CN | 🟢 中 | ~30 RPM | 429 + CAPTCHA | 10-30 分钟 |
| 360 | 🟢 中 | ~25 RPM | 限流弹窗 | 5-15 分钟 |
| Sogou (网页) | 🟢 中 | ~25 RPM | 503 / 验证码 | 5-15 分钟 |
| Sogou 微信 | ⚠️ 高 | ~15 RPM | 验证码滑块 | 30+ 分钟 |
| Toutiao | 🟢 中 | ~20 RPM | 限流页 | 10-20 分钟 |
| Shenma | 🟢 低 | ~30 RPM | 限制不严 | 几分钟 |
| Google | ⚠️ 高 | ~10 RPM（公开抓） | "unusual traffic" | 数小时 |
| DuckDuckGo HTML | 🟢 低 | ~30 RPM | 偶尔 202 | 几分钟 |
| Brave | 🟢 中 | ~20 RPM | "Too Many Requests" | 5-10 分钟 |
| Startpage | 🟢 低 | ~25 RPM | 偶发 429 | 几分钟 |
| WolframAlpha | 🟢 低 | ~30 RPM | 不易限流 | 几分钟 |

> ⚠️ 阈值是大致估计，实际触发点会因地区、IP 历史、UA 而异。

## 五级降级链

```
L1 触发：单引擎 HTTP 403/429/timeout
   ↓ 自动：retry 1 次 + UA 轮换 + 0.6s 退避
   ↓ 仍失败：标记该引擎 failed，继续其他引擎

L2 触发：多引擎失败（≥ 50% 引擎）
   ↓ 自动：脚本降级 --max-workers 2（建议重跑一次）
   ↓ 仍失败：进入 L3

L3 触发：所有引擎失败
   ↓ 自动：输出 "0 unique results" + Per-Engine Status 报告
   ↓ 用户决策：换网络 / 改 query / 切换 --engines 子集

L4 触发：用户判定环境问题
   ↓ 跑 python scripts/setup_check.py 全面体检
   ↓ 看 DNS / 实际 fetch 哪个环节失败

L5 触发：环境结构性问题（防火墙 / DNS 污染）
   ↓ 切到 VPN / 换 DNS / 稍后再试
   ↓ 用 web_fetch 单条试探，定位可访问的子集
```

## 错误码映射

| 错误 | 含义 | 自动应对 | 人工应对 |
|------|------|----------|----------|
| `URLError: timed out` | 引擎所在区域无法访问 | 标记 failed，继续 | 切换 --engines |
| `URLError: Connection refused` | 网络层阻断 | 标记 failed | 切 VPN |
| `HTTP 403` | 反爬触发 | retry 1 次（UA 轮换）| 降频 / 换引擎 |
| `HTTP 429` | 限流 | retry 1 次 + 退避 | 等 10-30 分钟 |
| `HTTP 503` | 服务方临时故障 | retry 1 次 | 等几分钟 |
| `HTTP 200 + 空结果` | 反爬验证页 / 关键词无结果 | 标记 0 results | 换 query / 换引擎 |
| `parser error` | HTML 结构变化（罕见）| 标记 failed | 升级 skill 版本 |

## 主动防护建议

### 单次会话限额

- 单次连续查询 ≤ 30 条（不是 search，是 query 数）
- 单次会话（~1 小时内）≤ 100 条
- 超过限额时主动 `time.sleep(600)` 10 分钟

### 缓存策略

```bash
# 把结果存成 JSON，下次直接复用
python scripts/multi_search.py "跨境电商 选品" --json results.json

# 重复查询时（24 小时内）
if os.path.exists("results.json"):
    age_h = (time.time() - os.path.getmtime("results.json")) / 3600
    if age_h < 24:
        print("cached")
        sys.exit(0)
```

### 错峰运行

- 9:00 / 14:00 / 21:00 是搜索引擎流量高峰，更易触发限流
- 凌晨 2:00–6:00 是低峰期，适合大批量跑

### 多 IP 轮换（如必须）

- 不在本 skill 内置（会增加复杂度）
- 在外部 cron 层做 IP 轮换（家宽 + 手机热点 + VPN 切换）

## 监测指标（推荐自动化层采集）

```python
# 每次 batch_search 完，输出到日志
{
  "ts": "2026-08-16T08:42:31+08:00",
  "queries": 5,
  "engines_attempted": 8,
  "engines_succeeded": 6,
  "unique_results": 23,
  "total_elapsed_s": 12.4,
  "per_engine_status": {"baidu": "0/403", "bing_cn": "ok/5", ...}
}
```

任何一项超过阈值：
- `engines_succeeded / engines_attempted < 0.5` → 网络/环境问题
- `unique_results < queries * 2` → query 太挑剔
- `total_elapsed_s > queries * 5` → 网络慢

## 常见误判

- ❌ "引擎 OK 但 0 results = 引擎坏了" → 不一定，**可能 query 无结果**
- ❌ "Bing 国内慢就是被限流" → 不一定，**可能是网络问题**
- ❌ "Google timeout = 脚本 bug" → 不一定，**Google 在国内就是访问不稳定**
- ✅ 看 Per-Engine Status：失败的引擎在 HTTP 200 但 0 results 时大概率是反爬或 query 无效；HTTP 4xx/5xx 是真网络问题