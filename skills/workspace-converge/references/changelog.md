# 版本变更与由来（出问题才需要读）

> 正文只留判断与顺序，踩过的坑记在这里。改规则前先扫一遍，避免把别人的教训再踩一次。

## v1.4.1 · 2026-11-04

**修 `converge.py` 路径核验的三类误报**（技能空间收敛时实测，报出的 4 处失效全是假阳性，逐条实测路径都在）：

- **不展开 `~`**：原实现直接 `os.path.exists()`，所有 `~/...` 写法必判失效 → 加 `expanduser` + `expandvars`。
- **不过滤占位符**：只跳过了 `*` 和 `…`，`<name>` 被当成真实路径 → 一并跳过含 `<` 的候选。
- **URL 咬尾**：`http://…` 被 `PATH_RE` 匹配成 `p:`（抠掉斜杠后只剩 `p:`）→ 跳过以 `:` 结尾、或含 `://` 的候选。
- 报告口径改为「有效候选数」而非「全部候选数」，噪声不再计入分母。

**反向验证**：造 `C:/no-such-dir-abc123/foo` 仍报「失效 1」，确认没修成"永远 PASS"——只去掉误报，保留真报。

**由来**：本空间 B 档收敛时路径项 FAIL 4 处，人工逐条核实后发现全是脚本问题。教训：**核验脚本本身也要被核验**，报 FAIL 先验证是记忆错还是脚本错，别急着回滚记忆。

## v1.4.0 · 2026-10-31

**对外改进（按技能成熟度模型 L2 → L3）**
- 新增 `evals/scenarios.md` 四个验收场景（正常 / 输入不全 / 误用边界 / 误删防护）——补上"改规则靠感觉"的缺口。
- 新增 `scripts/converge.py verify`：五项核验从四条人肉命令收成一条，退出码即判定。
- 新增 `scripts/converge.py snapshot`：快照 + 逐文件 md5 校验，让"备份存在"升级为"备份可恢复"。
- 正文新增「何时不要用」；A 档收紧为"纯问答轮不记结论"。
- 「由来」「处置表格式」「归档索引模板」「收敛记录模板」下沉到 `references/`，正文瘦身。
- 收敛记录新增三个数：耗时、字符前后、处置条数。

## v1.3.0 · 2026-10-29 傍晚
第 12 条旧判据"有 argparse 且无写死盘符"实测全盘失效——12 个脚本全无 argparse、全有盘符，按字面连天天在用的 `verify_sync.py` 都该归档。改为**技术层（盘符在模块级常量 vs 散在函数内）+ 业务层（产物是否还活着）**两层判据，用 AST 遍历判断。

## v1.2.0 · 2026-10-29 下午
① 压缩没有算法、只有判断，须写清"凭什么删" → 第 9 条补"别处有副本的只留指针"；② 实测压到 2,936 字符却 71 行、memcheck 仍报绿 → 第 10 条加行数核验，四项改五项；③ 把博客二手数据当一手（称 91.8k★，连接器实测 97,009★）→ 第 2 条加来源层级与时点；④ 只保证"一条没丢"，用户无法验证 → 第 21 条要求处置表。

## v1.0.0 → v1.1.0 · 2026-10-29 上午
- 手工令牌比对号称零丢失，脚本复测发现漏 3 个指针（台账空间 ID、回滚点全路径、build_publish 路径）→ 第 10 条改为脚本产生清单。
- 由空间文件上移为技能：方法随仓库走（sync.sh / restore.sh），触发词双保险（技能 description + 用户级记忆）。

## 更早的教训（写进正文条款）

| 日期 | 事故 | 落到哪条 |
|---|---|---|
| 2026-10-27 | 误删暂存目录内 15 条记忆原件（三处无副本） | 第 3、15 条 |
| 2026-10-27 | 全空间收敛实测：poker 25 个、台账 16 个令牌零丢失、16 处路径 exists 全过 | 第 10 条 |
| 2026-10-26 | AST 判盘符路径（朴素正则误把 `http://` 当路径） | 第 12 条 |

## 外部调研结论（勿重复查）

- `agent-almanac/prune-agent-memory`：自我检查不算核验、需外部锚点、删除留审计账、压缩时不新写
- `moltq` / `pearceit` 生产实践：推测词被压缩拔高成定论是高频隐性损伤
- `rem-sleep`：分档（Consolidate / Defrag）、拿不准就保留
- `memory-merger`：两条记忆冲突时不自己选边
- OpenClaw 社区：重要内容前置（截断从尾部开始）、频繁重写破坏缓存
- 技能工程标准（2026-10）：成熟度 L0-L5、可验证逻辑必须脚本化、≥3 个 eval 场景、正文 <5,000 tokens
- 不采用：letta / cognee 类向量库方案（要服务、要 key、不可人读）

## v1.5.0（2026-11-08）忘坑与止损

**问题**：坑记了但召回靠模型自觉（卡片 resume 是 instruction-gated），跨空间的坑更是看不见；返工无熔断（一翔 6 脚本作废、核对写 5 遍——换了说法没换事没人拦）。

**外部依据**（2026-11-08 调研，勿重复查）：
- AgentsMesh：recall 靠规则提醒必然失败，改 hook（动作前确定性注入）才 deterministic——"Models don't remember to ask"
- enso-os（94★）：SessionStart 注入 lessons、rules in code not prompts、"200 行 hooks > 800 行 prompt"
- ShieldCortex：stored memory ≠ active memory，纠错埋在散文里配不上当前问题
- TradeMemory：预飞检查——先召回教训再行动，红灯即停
- 熔断阶梯（CSDN/xzhibot）：同一做法第 2 次失败必须停并报告；终止三判据（成功/失败/放弃）

**换机后重注册 hook**（settings.json 是账号级不进仓库；让助手改 settings.json 即可）：
在 `%USERPROFILE%\.workbuddy\settings.json` 的 `hooks.SessionStart` 数组追加：
`{"matcher":"","hooks":[{"type":"command","command":"\"<python3.13绝对路径>\" \"%USERPROFILE%\\.workbuddy\\skills\\workspace-converge\\scripts\\pitfall_inject.py\"","timeout":10,"metadata":{"managed_by":"pitfall-reminder"}}]}`
验证：新会话开头应出现 `<pitfall-reminder>` 段；`pitfalls/inject.log` 有当次记录。

**变更**：
- 新增「止损三条款」（返工熔断/方向门/放弃判据）——干活时生效，不等收尾
- A 档记坑必填**触发场景**；复发≥2 或跨空间 → 晋升 `references/pitfalls-INDEX.md`（SessionStart hook 数据源，scripts/pitfall_inject.py 每会话注入前 6 条；脚本与索引都在技能内＝随 sync.sh 仓库走，换机 restore 后重注册 hook 即可，注册命令见下）
- A 档新增止损回填：止损原因当场写成坑
- B 档新增第 15 条坑体检：MEMORY 坑逐条判定晋升/留置/失效
- 配套：my-project-card 2.0.1 简报置顶「⚠ 开工先读：坑与已排除」（card.py grab_section，acceptance 30/30）
- 场景 E5（止损）加入 evals
