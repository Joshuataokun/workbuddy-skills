---
name: prompt-rewrite-guard
description: "优化、改写、收紧或压缩已有的提示词 / 系统提示词 / SKILL.md / Agent 指令：先冻结原有约束条款，再做最小改动，最后用验收用例对比改前改后的通过率。使用时机：当用户贴出一段已有的提示词、指令、规则或 SKILL.md 并表达任何修改意图时使用——包括「帮我优化提示词」「这段提示词不生效」「AI 老是不按格式来」「把这个 skill 写严一点」「规则写死」「压缩到七成但不许丢规则」「删掉冗余但别丢要求」「输出不稳定」「这段系统提示词太啰嗦」。即使用户没说「提示词」三个字，只要给的是已有文本并要求改写、加固或精简，也应当使用本技能。触发词：优化提示词、改提示词、重写提示词、收紧提示词、压缩提示词、提示词不生效、提示词不稳定、提示词太啰嗦、输出格式不固定、按格式输出、写严一点、写死规则、删减规则、验收用例、回归对比、按守门员流程、走 prompt-rewrite-guard。不适用：从零创作文案、写诗写故事、纯翻译、纯代码实现——这类任务没有「已有条款」需要保护。"
display_name: "提示词改写守门员（本地版）"
display_name_en: "prompt-rewrite-guard (local)"
description_zh: "优化、改写、收紧或压缩已有的提示词 / 系统提示词 / SKILL.md / Agent 指令：先冻结原有约束条款，再做最小改动，最后用验收用例对比改前改后的通过率。使用时机：当用户贴出一段已有的提示词、指令、规则或 SKILL.md 并表达任何修改意图时使用。即使用户没说「提示词」三个字，只要给的是已有文本并要求改写、加固或精简，也应当使用本技能。触发词：优化提示词、改提示词、重写提示词、收紧提示词、压缩提示词、提示词不生效、提示词不稳定、提示词太啰嗦、输出格式不固定、写严一点、写死规则、删减规则、验收用例、回归对比、按守门员流程。不适用：从零创作文案、写诗写故事、纯翻译、纯代码实现。"
description_en: "Optimize, rewrite, tighten or compress an existing prompt, system prompt, SKILL.md or agent instruction: freeze the original constraints first, make the smallest authorized change, then prove it with a before/after acceptance-case pass rate. Use when the user pastes an existing prompt, instruction set, rule list or SKILL.md and asks to change it in any way - optimize it, make it stricter, lock the output format, compress it without dropping rules, or fix unstable output. Use this even when the user never says the word prompt but clearly supplies existing text to be rewritten, hardened or trimmed. Do not use for writing copy from scratch, fiction or poetry, plain translation, or code implementation - there are no existing constraints to protect."
version: 2.1.0
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

## Mandatory Gate: Optimizing / Rewriting an Existing Prompt

Applies whenever the user asks to optimize, rewrite, fix, polish, strengthen, broaden or tighten an existing prompt / system prompt / custom instructions. Pure typo or formatting fixes may use the light mode in `references/optimization-workflow.md`. Load that file for the checklist, attribution, regression and delivery formats, and `references/eval-cases.md` for the acceptance-case suite. Run all steps **before saving any file and before the final reply**.

1. **Visible criteria ledger (before rewriting)**: show a C-numbered list of every criterion in the source and every hard condition from the user. For each item record: the object set, the dimensions required for each object, universal quantifiers (each / both / all), ranking and counts, thresholds, numeric precision, source constraints, and exceptions. When a rule covers several objects, give each object its own entry. Do not let one example stand in for the full object × dimension set.
2. **Failure attribution (before rewriting)**: state what is actually wrong with the current prompt before proposing any change. One row per observed or reported failure: symptom → root cause → the C-item(s) it touches → evidence (verbatim quote, line number, or a failing case). If the user gave no failure signal, say so and record the goal as a request rather than a defect. Do not start rewriting while the table is empty or speculative.
3. **Ambiguity and authorization**: list underspecified or conflicting items, such as time window, judgment basis, data source, runtime-injected text, subjective intensity, or contradictory meta-requests. Vague requests ("optimize", "make it broader", "more accurate") do not authorize changing a hard criterion. List each proposed change to a C-item as a concrete confirmation question and wait for an answer. If the user forbids questions, keep the original criterion and state that.
4. **Bounded change**: make only the changes the user named or confirmed. Do not invent facts, settings, sources, sections, or requirements. List new ideas separately as *optional suggestions*, never as mandatory rules in the rewrite. Do not delete, loosen, narrow, or add exceptions to any C-item without authorization.
5. **Change ledger and re-verification (after rewriting)**: map every C-item to its location in the new draft and mark it `kept / rewritten / deleted / added`, with the reason and the authorization source. Re-check the full object × dimension combinations against the draft. Then check internal consistency, meaning each key term has one definition throughout. If behavior depends on runtime-injected content, state that prompt-side wording can only mitigate the problem and specify the change needed on the injection side.
6. **Regression comparison (before saving)**: run the cases in `references/eval-cases.md` against the **original** prompt first and record the baseline, then run the same cases against the draft. Deliver a before/after table marked `kept / improved / regressed` per case. Any regression blocks delivery. Record the backup path of the original file as the rollback point. Never claim an improvement the table does not show.
7. **Stop conditions**: if any C-item is lost, narrowed, or given a new exception without authorization, or if the ledger and the draft disagree, or if any acceptance case regresses, or if the draft passes only by weakening a C-item, do not save or deliver. Fix the draft or ask the user.
8. **Honest delivery**: include the ledger, a per-requirement hit table, the before/after pass table, the rollback path, assumptions, reproducible test cases, and an uncertainty statement. Containing a rule in text is not the same as a verified effect. Mark gains in accuracy, completeness, and similar qualities as `pending verification` unless they were actually executed and observed. Never claim "all constraints preserved", "fixed", or "no problems" unless the ledger and tests support it.

## Use Cases

- Refining vague or ineffective prompts
- Creating specialized system prompts for specific domains
- Designing custom instructions for AI agents and skills
- Optimizing prompts for consistency and reliability
- Teaching prompt engineering best practices
- Debugging prompt performance issues
- Creating prompt templates for reusable workflows
