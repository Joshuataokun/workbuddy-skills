# Multi Search Engine

聚合 17 个搜索引擎（8 国内 + 9 国际）的**零 API Key** 搜索工具，含真正可执行的 Python 调度脚本。

## 30 秒上手

```bash
# 1. 环境自检
python scripts/setup_check.py

# 2. 立刻跑一次
python scripts/multi_search.py "你的关键词"

# 3. 批量跑多个
python scripts/batch_search.py --file queries.txt --md
```

详细文档：[SKILL.md](./SKILL.md)

## 核心特性

- ✅ **17 引擎覆盖**：8 国内（百度、必应中国/国际、360、搜狗、微信、头条、神马）+ 9 国际（Google、DDG、Brave、Startpage、Qwant、Ecosia、Yahoo、WolframAlpha）
- ✅ **零 API Key**：所有引擎走公开 HTML 抓取
- ✅ **零依赖**：纯 Python 3.8+ stdlib，不装第三方包
- ✅ **优雅降级**：单引擎失败不影响其他引擎
- ✅ **真实可执行**：scripts/multi_search.py 经过实战测试（std-lib-only）

## 文件结构

```
multi-search-plus/
├── SKILL.md                       主入口文档
├── metadata.json                  平台元数据
├── config.json                    引擎 URL 配置
├── CHANGELOG.md                   版本历史
├── scripts/
│   ├── multi_search.py            并行调度器
│   ├── setup_check.py             环境预检
│   └── batch_search.py            批量查询
├── examples/                      5 个真实场景示例
├── references/                    引擎高级语法 + 反模式
└── knowledge-base/                速率限制与降级
```

## License

MIT