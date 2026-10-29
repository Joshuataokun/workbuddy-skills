---
name: prompt-rewrite-guard
description: "优化、改写、收紧或压缩已有的提示词 / 系统提示词 / SKILL.md / Agent 指令：先冻结原有约束条款，再做最小改动，最后用验收用例对比改前改后的通过率。使用时机：当用户贴出一段已有的提示词、指令、规则或 SKILL.md 并表达任何修改意图时使用——包括「帮我优化提示词」「这段提示词不生效」「AI 老是不按格式来」「把这个 skill 写严一点」「规则写死」「压缩到七成但不许丢规则」「删掉冗余但别丢要求」「输出不稳定」「这段系统提示词太啰嗦」。即使用户没说「提示词」三个字，只要给的是已有文本并要求改写、加固或精简，也应当使用本技能。没有原文、只有一句模糊想法或抱怨，而要的是一段提示词 / 指令 / 规则时也用它——「我想要 AI 帮我干某某事，怎么写」「它老是不按我想的来，我该怎么跟它说」「帮我想清楚我到底要什么」「怎么说 AI 才懂」——这时走反推模式：先自己查、只问查不到又只有你能拍板的、把没说出口的需求问出来，再产出意图卡和可直接用的提示词。触发词：优化提示词、改提示词、重写提示词、收紧提示词、压缩提示词、提示词不生效、提示词不稳定、提示词太啰嗦、输出格式不固定、按格式输出、写严一点、写死规则、删减规则、验收用例、回归对比、按守门员流程、走 prompt-rewrite-guard、怎么写提示词、我该怎么跟它说、帮我想清楚要什么、反推意图、意图卡。不适用：直接要成品内容（写文案、写诗写故事、纯翻译、纯代码实现）——这类任务没有提示词要反推，也没有已有条款要保护。"
display_name: "提示词改写守门员（本地版）"
display_name_en: "prompt-rewrite-guard (local)"
description_zh: "优化、改写、收紧或压缩已有的提示词 / 系统提示词 / SKILL.md / Agent 指令：先冻结原有约束条款，再做最小改动，最后用验收用例对比改前改后的通过率。有原文要改时走守卫模式；没有原文、只有一句模糊想法或抱怨而要一段提示词时走反推模式——先自己查、只问查不到又只有你能拍板的，把没说出口的需求问出来，再产出意图卡和提示词。触发词：优化提示词、改提示词、压缩提示词、提示词不生效、输出格式不固定、写严一点、写死规则、验收用例、回归对比、按守门员流程、怎么写提示词、我该怎么跟它说、帮我想清楚要什么、反推意图、意图卡。不适用：直接要成品内容（文案、诗、故事、翻译、代码实现）。"
description_en: "Optimize, rewrite, tighten or compress an existing prompt, system prompt, SKILL.md or agent instruction: freeze the original constraints first, make the smallest authorized change, then prove it with a before/after acceptance-case pass rate. Use when the user pastes an existing prompt, instruction set, rule list or SKILL.md and asks to change it in any way - optimize it, make it stricter, lock the output format, compress it without dropping rules, or fix unstable output. Use this even when the user never says the word prompt but clearly supplies existing text to be rewritten, hardened or trimmed. Also use it when there is no source text at all and the user only has a vague wish or complaint but wants a prompt, instruction or rule - for example 'how do I tell the AI to do X', 'it never does what I meant, how should I phrase it', 'help me work out what I actually want'. That runs the excavation mode: research first, ask only what cannot be looked up and only the user can decide, recover the requirement the user never said out loud, then deliver an intent card plus a usable prompt. Do not use it when the user wants finished content directly - copywriting, fiction, poetry, plain translation, or code implementation - because there is no prompt to excavate and no existing constraints to protect."
version: 2.3.0
agent_created: true
---

# Prompt Engineering Expert Skill

This skill equips Claude with deep expertise in prompt engineering, custom instructions design, and prompt optimization. It provides comprehensive guidance on crafting effective AI prompts, designing agent instructions, and iteratively improving prompt performance.

## Capabilities

- **Prompt Writing Best Practices**: Expert guidance on clear, direct prompts with proper structure and formatting
- **Custom Instructions Design**: Creating effective system prompts and custom instructions for AI agents
- **Prompt Optimization**: Analyzing, refining, and improving existing prompts for better performance
- **Advanced Techniques**: Chain-of-thought prompting, few-shot examples, XML tags, role-based prompting
- **Evaluation & Testing**: Developing test cases and success criteria for prompt evaluation
- **Anti-patterns Recognition**: Identifying and correcting common prompt engineering mistakes
- **Context Management**: Optimizing token usage and context window management
- **Multimodal Prompting**: Guidance on vision, embeddings, and file-based prompts

This skill runs in two modes. **Guard mode** rewrites an existing prompt without losing a single existing requirement. **Excavation mode** starts from a vague wish with no source text, asks only what cannot be looked up, and reconstructs the prompt the user actually needed but never said. Pick the mode first; the rules below are not interchangeable.

## Mode Router — 先选模式

**判定顺序固定，不可倒置。**

1. **有没有已有文本要被改写？** 有 → **守卫模式**（下一节 Mandatory Gate，8 步）。没有 → 第 2 步。
2. **用户要的是不是一段提示词 / 指令 / 规则？** 是 → **反推模式**（见下文 Excavation Mode）。不是（要文章、要诗、要翻译、要代码成品）→ 两个模式都不走，一句话说明不适用，然后正常帮他做那件事。
3. **有原文，也说要改，但缺口扫描发现原文本解决的根本不是他要的问题** → 先反推、后守卫：先出意图卡确认，确认后再把那版原文当「原文」冻结账本走 8 步，并在交付里写明「原本要解决的不是这个」。

| 用户手里有什么 | 模式 | 入口 |
|---|---|---|
| 一段已有的提示词 / 规则 / SKILL.md，要改 | 守卫 | Mandatory Gate（8 步） |
| 只有一句模糊想法、抱怨或目标，没有原文 | 反推 | Excavation Mode（E1–E5） |
| 有原文，但真正想问的是另一件事 | 反推 → 守卫 | 先意图卡，后 8 步 |

## 交付契约 — 两个模式都适用，优先于下文所有交付格式

用户要的是**在对话里复制就能用**的提示词，不是一份要点开才能看的报告，也不是一份要他自己再判断、再改的半成品。

1. **提示词直接显示在回复里。** 终稿放进一个 ` ```text ` 代码块，整段一次复制就能粘进 WorkBuddy 指令框；代码块外不夹提示词正文。一次只给一版终稿，不给 A/B 版让他挑。
2. **不生成新文件。** 不写 .md / .txt 报告，不把账本、表格存盘，不让他「点开文件查看」。唯一例外：被改的原文本身就是本地文件（如 SKILL.md）——先备份，再写回原文件，并且**仍然**在回复里给出改后的全文或改动段落。
3. **提示词正文不用表格。** 目标默认是 WorkBuddy 指令框（纯文本，`查得`）：用编号列表和短句，不用 Markdown 表格、`<br>`、嵌套代码块。原文本身带表格时保留原表（属于 C 项，不擅改），在摘要里提示「含表格，粘贴后可能错位，要转成列表吗」。
4. **不清楚就先问，问完自己出终稿。** 会改变提示词写法、又只有用户能拍板的点，在**出稿之前**问：有点选提问工具就用它（每题 2–4 个选项，推荐项排第一并写一句理由，标明不选时的默认）；没有就用编号文字题，写明「回复『默认』即全按推荐，也可回 1b 2a」。一次问完，≤5 题，不附半成品。用户答完直接给**完整终稿**：不留 `[待填]` / `XXX` 占位，不写「不对你再自己改」，不让他回头比对。影响小的点不问，按默认写进正文，在摘要里列出。
5. **过程压成摘要，放在代码块下面，≤4 行。** 守卫模式：`条款：保留 a / 改写 b / 删除 c / 新增 d（改动均经授权）`｜`回归：跑 N 条，退步 0`｜`回滚：<备份路径>` 或 `无文件改动`｜`效果：待实跑验证`。反推模式：`理解：一句话`｜`我替你定的：……（逐条标 查得 / 猜的）`。账本、归因、命中表、回归对比等完整表格**内部照做、默认不展示**；用户说「要明细 / 看账本」时再给。退步、未授权改动、未跑的用例**不许因为压缩而省略**——有就必须写进摘要。
6. **还要改，说一句就行。** 摘要最后一行固定：`要改哪条直接说（如「第 3 条改成……」），我出新的完整版。` 用户提出修改后，以当前终稿为原文走守卫模式，重新给完整终稿，不让他自己拼接。

**不许互相顶替**：守卫管的是**不丢条款**，反推管的是**问出没说出口的**。不许因为「反推看起来更快」就把该走守卫的请求拉进反推——那会把用户已有的硬要求丢掉；也不许因为「守卫更严」就把没有原文的模糊需求硬套 8 步——那会在一份不存在的账本上空转。

## Mandatory Gate: Optimizing / Rewriting an Existing Prompt

Applies whenever the user asks to optimize, rewrite, fix, polish, strengthen, broaden or tighten an existing prompt / system prompt / custom instructions. Pure typo or formatting fixes may use the light mode in `references/optimization-workflow.md`. Load that file for the checklist, attribution, regression and delivery formats, and `references/eval-cases.md` for the acceptance-case suite. Run all steps **before saving any file and before the final reply**.

1. **Visible criteria ledger (before rewriting)**: show a C-numbered list of every criterion in the source and every hard condition from the user. For each item record: the object set, the dimensions required for each object, universal quantifiers (each / both / all), ranking and counts, thresholds, numeric precision, source constraints, and exceptions. When a rule covers several objects, give each object its own entry. Do not let one example stand in for the full object × dimension set.
2. **Failure attribution (before rewriting)**: state what is actually wrong with the current prompt before proposing any change. One row per observed or reported failure: symptom → root cause → the C-item(s) it touches → evidence (verbatim quote, line number, or a failing case). If the user gave no failure signal, say so and record the goal as a request rather than a defect. Do not start rewriting while the table is empty or speculative.
3. **Ambiguity and authorization**: list underspecified or conflicting items, such as time window, judgment basis, data source, runtime-injected text, subjective intensity, or contradictory meta-requests. Vague requests ("optimize", "make it broader", "more accurate") do not authorize changing a hard criterion. List each proposed change to a C-item as a concrete confirmation question and wait for an answer. If the user forbids questions, keep the original criterion and state that.
4. **Bounded change**: make only the changes the user named or confirmed. Do not invent facts, settings, sources, sections, or requirements. List new ideas separately as *optional suggestions*, never as mandatory rules in the rewrite. Do not delete, loosen, narrow, or add exceptions to any C-item without authorization.
5. **Change ledger and re-verification (after rewriting)**: map every C-item to its location in the new draft and mark it `kept / rewritten / deleted / added`, with the reason and the authorization source. Re-check the full object × dimension combinations against the draft. Then check internal consistency, meaning each key term has one definition throughout. If behavior depends on runtime-injected content, state that prompt-side wording can only mitigate the problem and specify the change needed on the injection side.
6. **Regression comparison (before saving)**: run the cases in `references/eval-cases.md` against the **original** prompt first and record the baseline, then run the same cases against the draft. Deliver a before/after table marked `kept / improved / regressed` per case. Any regression blocks delivery. Record the backup path of the original file as the rollback point. Never claim an improvement the table does not show.
7. **Stop conditions**: if any C-item is lost, narrowed, or given a new exception without authorization, or if the ledger and the draft disagree, or if any acceptance case regresses, or if the draft passes only by weakening a C-item, do not save or deliver. Fix the draft or ask the user.
8. **Honest delivery**: produce the ledger, a per-requirement hit table, the before/after pass table, the rollback path, assumptions, reproducible test cases, and an uncertainty statement. Present them per the 交付契约: the final prompt in a chat code block first, then the ≤4-line summary; the full tables are shown only when the user asks for details, and any regression, unauthorized change, or unrun case must still appear in the summary. Containing a rule in text is not the same as a verified effect. Mark gains in accuracy, completeness, and similar qualities as `pending verification` unless they were actually executed and observed. Never claim "all constraints preserved", "fixed", or "no problems" unless the ledger and tests support it.

## Excavation Mode — 反推没说出口的提示词

用在用户只有一句想法、抱怨或目标，而要的是一段提示词 / 指令 / 规则的时候。目标是**用最少的问题，问出他没表达出来的那部分**，然后给一份他能直接用、也能一眼改的东西。

五步，顺序不可跳。分类细节、每类问法、问题库、意图卡模板见 `references/intent-excavation.md`。提问一律按「交付契约」第 4 条的机制执行（点选工具优先、一次问完、问完自己出完整终稿）。

### E1 · 先查后问

**能自己查到的一律不问。** 按顺序查：用户这段话本身 → 本次会话已说过的 → 已附的文件 / 目录 / 代码 / 表格 / 截图 → 环境与工具 → 行业惯例与常识。查到的东西在意图卡里标 `查得` 并写出依据。

**只有同时满足三条才配占一个提问位**：① 查不到；② 会改变提示词的写法；③ 只有用户能拍板（方向取舍、验收裁量、风险偏好、篇幅预算、谁看结果）。

三条缺一条就不许问——尤其第 ② 条：问了也不影响写法的，是白问。

### E2 · 缺口扫描（六类）

逐类打 `Clear / Partial / Missing`，只对 Partial 和 Missing 生成候选问题。

| 类别 | 问的是 | 不定的后果 |
|---|---|---|
| G1 目标与完成态 | 跑起来什么算成功？谁看一眼能判定？ | 方向漂移，写出来的东西对不上他的用场 |
| G2 对象与范围 | 对谁做、做几个、含什么、明确不含什么 | 越界扩写或漏项 |
| G3 输入与来源 | 喂什么进去、从哪来、多长、质量差怎么办 | 提示词只对理想输入有效 |
| G4 输出形态与精度 | 格式、结构、长度、要不要数字/引用/单位、精度 | 每次格式都不一样，反复返工 |
| G5 边界与例外 | 冲突怎么办、信息不够怎么办、不许做什么 | 出边界就乱编 |
| G6 取舍与优先级 | 快 / 全 / 准 打架时先保哪个 | 冲突时按最省力的方式走（通常是偷懒那条） |

### E3 · 定档（决定问几个）

候选问题按 **影响 × 不确定** 排序——影响 = 答错会让提示词整体作废的程度；不确定 = 你猜中的概率有多低。然后按下表定档：

| 高影响缺口 | 档位 | 动作 |
|---|---|---|
| 0–2 个 | **0 问档** | 不问。直接出稿，补的缺口全部写进意图卡「我替你定的」，一次交给他改 |
| 3–5 个 | **轻问档** | 一轮问完，全部一次发出，**不再追加第二波** |
| ≥6 个 | **深挖档** | 一轮发 ≤5 个（硬上限），其余进「待裁决清单」，出稿时说明这些没定 |

**硬上限 5，任何档位都不许破。** 超过 5 个说明这活太大——先拆成几件、一次反推一件，并告诉他为什么拆。

**默认走 0 问档。** 只有「猜错就整份白写」的缺口才值得占一个提问位。宁可先给一版带假设的，让他指着改，也不要先问五个问题再开工。

### E4 · 提问规则（六条，全是硬的）

1. **一轮发完，不许挤牙膏。** 所有问题在同一条消息里给全，他答一次就该够。不允许「答完这个我再问下一个」。
2. **每题必须能短答。** 给 2–4 个互斥选项，标出推荐项和一句话理由，并允许他直接写自己的答案。禁止开放式问题——「你想要什么样的输出」是无效问题，「输出要多长：三行内 / 一屏 / 不限（推荐一屏）」才是有效问题。
3. **每题必须自带默认值。** 写清「你不答我就按 X 走」。他没答不等于卡住。
4. **问决定写法的，不问决定内容的。** 「输出要多长」有效；「你想写什么」无效——那是他的活，不是格式问题。
5. **不重复问、不问已经说过的、不问查得到的、不问他说过不用问的。**
6. **他说「别问了 / 就按你理解 / 快点」→ 立刻停问**，转 0 问档，未定项全部标 `猜的` 写进意图卡，并用一句话说明哪里可能会偏。

**提问时不附半成品提示词。** 先问清再写，避免他拿着半成品去用、以后再也分不清哪版是对的。

### E5 · 交付：意图卡 + 提示词

两块，顺序固定，不要中间夹解释。

**第一块 · 意图卡**（四列表，他只看这张就能改）

列固定为：**你要的**（引用原话，一字不改）｜**我按这个理解**（一句可执行的理解）｜**我替你定的**（默认值 + 一句为什么，逐条标 `查得` / `猜的`）｜**还需你拍板**（剩余高影响缺口，按影响排序，各带默认值；都定了就写「无」）。

完整表样与三个实例见 `references/intent-excavation.md`。表里不写解释段落——要解释就写进「我替你定的」的括号里。

**第二块 · 提示词**（代码块包住，整段可复制）

- 用他的语言写，正文里不夹解释、不夹「以下是为你优化的提示词」这类废话。
- 结构按需取：角色/背景（非必要不写）→ 任务 → 输入说明 → 输出格式与精度 → 边界与例外 → 冲突优先级。
- 意图卡「我替你定的」里的默认值**全部写进正文**，并在末尾加一行：`第 X 条、第 Y 条是默认假设，不对就改这两句。`
- 长度服从 G4 的结论；他没说就按「够用即止」，不堆形容词、不写排比。

**交付之后**：他一旦开始改这段提示词本身，立刻转守卫模式，把那版当「原文」冻结账本——反推产出的东西也会被人改坏。

## Use Cases

- Refining vague or ineffective prompts
- Creating specialized system prompts for specific domains
- Designing custom instructions for AI agents and skills
- Optimizing prompts for consistency and reliability
- Teaching prompt engineering best practices
- Debugging prompt performance issues
- Creating prompt templates for reusable workflows
- 从一句模糊需求反推出一段完整提示词（手上没有原文时）—— Excavation Mode
- 用户说不清自己想要什么，需要先被问对那几个问题
- 一次性任务的提示词：他只有目标，没有稿子
