# prompt-rewrite-guard（本地版）

> **这是本地技能，不连市场**：没有 `_skillhub_meta.json`、没有 skillId、不显示原作者，市场更新不会碰它。
> 内容来自 `prompt-engineering-expert` v1.0.1 的本地改造（v2.0.0），之后所有修改都在这个目录里独立演进。

**中文速览**：改写/优化提示词时，先冻结原有要求（C 项账本），再问清歧义，只做已授权的改动，最后用验收用例对比改前改后的通过率。改坏了能一句话退回。

**v2.0.0 变化**：新增"失败归因"与"回归对比"两道关卡，新增 `references/eval-cases.md`（8 条验收用例）。原有知识与技巧未改动。

## 什么时候用

- 已有提示词 / skill 效果不稳，想知道问题在哪
- 要把规则写严、写死，或把啰嗦的系统提示词压缩但不怕丢规则
- 要判断"改完到底变好没有"

不适用：从零写文案、写诗写故事、纯翻译、纯代码实现。

## 目录结构（与磁盘一致，改文件请同步本表）

```
prompt-rewrite-guard/
├── SKILL.md                       技能入口：能力清单 + 强制关卡（8 步）
├── CLAUDE.md                      7 大领域知识清单
├── README.md                      本文件
├── docs/
│   ├── BEST_PRACTICES.md          规范、skill 结构、命名、token 预算
│   ├── TECHNIQUES.md              CoT / Few-shot / XML / 角色 / 链式 / 上下文 / 多模态
│   └── TROUBLESHOOTING.md         8 类症状 + 5 步调试
├── examples/
│   └── EXAMPLES.md                10 个 before/after 案例
└── references/
    ├── optimization-workflow.md   账本 / 归因 / 变更 / 回归 / 交付 的表格格式
    ├── eval-cases.md              8 条验收用例（正常·边界·冲突·攻击）
    └── trigger-tests.md           17 条触发自测（改完描述后人工跑一遍）
```

## 强制关卡（8 步）

1. 冻结账本 — C 项全量枚举
2. 失败归因 — 现象→根因→涉及 C 项→证据（空表不许动手）
3. 歧义与授权 — 逐条确认
4. 有界改动 — 新想法只进"可选建议"
5. 变更账本 — kept / rewritten / deleted / added + 授权来源
6. 回归对比 — 同一批用例，改前 vs 改后，回归即停
7. 停止条件 — 丢条款、账本不符、用例回归，一律不交付
8. 诚实交付 — 账本 + 通过率表 + 回滚路径 + 待验证声明

## 维护约定

- 改 `SKILL.md` 前先备份原文件，备份路径写进交付说明。
- 新增文件必须同步上面的目录表（旧版 INDEX 就因漏列 `references/`，导致新会话可能找不到工作流）。
- 体积预算（当前实测）：`SKILL.md` ≤ 8 KB（现 7.1 KB），单个 references ≤ 6.5 KB（现 5.8 KB），全目录 ≤ 62 KB（现 58.4 KB）。超了按 导航 → 重复 → 旧案例 的顺序砍。
- 改 `description` 时同步 `description_zh` / `description_en`，三者都要带触发场景同义词与负例。
