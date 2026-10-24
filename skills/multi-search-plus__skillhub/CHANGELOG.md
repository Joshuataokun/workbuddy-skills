# Changelog

## v2.2.0 (2026-08-16)
- **R 可靠性 4.0 → 目标 ≥ 4.5**：新增 `scripts/multi_search.py` 真正可执行的并行搜索引擎调度器（stdlib only，零依赖）
- **E 有效性 4.2 → 目标 ≥ 4.5**：新增 `scripts/setup_check.py`（13 项环境预检）+ `scripts/batch_search.py`（多 query 批量 runner）
- **A 适用性 4.3 → 目标 ≥ 4.7**：新增 `knowledge-base/rate-limits.md`（速率限制 + 5 级降级链 + 错误码映射）
- **C 规范性 4.5 → 目标 ≥ 4.8**：新增 `references/anti-patterns.md`（10 条反模式清单 + 速查决策表）
- **examples/**：5 个真实业务场景完整示例（中文搜索 / 跨境电商 / 微信 / 学术 / 隐私）
- **SKILL.md**：重写主入口，30 秒上手、Trigger Flow 图、决策树、三条调用路径
- **元数据**：metadata.json / config.json 全部对齐 v2.2.0

## v2.0.1 (2026-02-06)
- 精简文档，优化发布

## v2.0.0 (2026-02-06)
- 新增 9 个国际搜索引擎
- 强化深度搜索能力

## v1.0.0 (2026-02-04)
- 初始版本：8 个国内搜索引擎