# Prompt Optimization Gate — Formats and Templates

Load this file when the user asks to optimize or rewrite an existing prompt. It gives the formats for the gate steps in `SKILL.md`. The rules themselves live in `SKILL.md`; this file covers formats only.

## Light mode

If the request is limited to typos, wording polish with no semantic change, or formatting, a short ledger is enough. List only the C-items touched and confirm that no other criterion changed. Use full mode as soon as any criterion's meaning, scope, threshold, or structure would change.

## 1. Criteria ledger format (shown to the user before rewriting)

| ID | Source location | Object set | Dimensions per object | Quantifier | Ranking / count | Threshold | Precision | Source constraint | Exceptions |
|---|---|---|---|---|---|---|---|---|---|
| C1 | §x line y | {A, B} | A: d1,d2; B: d1,d2 | each / both / all | top-N + bottom-N | ... | ... | ... | none |

Expansion rule: if a criterion says "A and B both need X", or "for each object do Y", either split it into C1a/C1b or list every object explicitly in the row. Cross-check each object × dimension cell when you verify.

Also record the user's own meta-requests as U1, U2, …. Examples are "more accurate", "broader", and "more structured".

## 2. Failure attribution table (before rewriting)

| ID | Symptom (observable) | Root cause | C-item(s) touched | Evidence (quote / line / failing case) |
|---|---|---|---|---|
| A1 | e.g. output format drifts on long inputs | format rule only stated once, no enforcement clause | C3 | original §2 line 4; case E1 fails |

Rules:
- One row per distinct failure. Merge duplicates, do not pad.
- Evidence must be a verbatim quote, a line number, or a named case. "Feels weak" is not evidence.
- If the user reported no failure, write one row: `no failure signal — goal is a request, not a defect`, and treat the change as an enhancement rather than a fix.
- An empty or speculative table blocks the rewrite.

## 3. Ambiguity / authorization list

| ID | Item | Why it is ambiguous or which C-item it touches | Options (2–4) | Status (confirmed / declared default / waiting) |
|---|---|---|---|---|

Common categories:
- Time window and time zone.
- Judgment basis and undefined thresholds.
- Data-source priority and conflicts.
- Runtime-injected content: RAG, knowledge base, tool output.
- Subjective intensity: offer a measurable lever such as count, threshold, required or banned phrasing, or length.
- Contradictory meta-requests.

Any option that changes a C-item counts as a change to a hard criterion. Wait for the user to confirm it.

## 4. Change ledger format (after rewriting, before saving)

| ID | New location | Action (kept / rewritten / deleted / added) | Diff summary | Reason | Authorization (user msg / U-id / none) |
|---|---|---|---|---|---|

Rules:
- Every C-item appears exactly once.
- Any `deleted`, any narrowing, and any new exception or precision change on a C-item needs a non-empty authorization. Otherwise, stop.
- `added` rows that the user did not request belong in "Optional suggestions", not in the mandatory body of the rewrite.

## 5. Regression comparison and rollback (before saving)

Run `references/eval-cases.md` twice: original prompt (baseline) → draft (after).

| Case | Category | Sealed | Baseline | After | Mark |
|---|---|---|---|---|---|
| E1 | normal | no | pass | pass | kept |
| E3 | edge | no | pass | fail | **regressed** |

Rules:
- Any `regressed` row stops delivery. Fix the draft or ask the user.
- `improved` requires a case that failed on the original and passes on the draft. Restating the same result is `kept`, not `improved`.
- Report the case count run and the count not run. Silent omission is a defect.
- Rollback point: record the absolute backup path of the original file. If the file was edited in place without a backup, create one before saving.

## 6. Pre-save self-check

- [ ] Each C-item, including every object × dimension cell, is present in the draft.
- [ ] No unauthorized deletion, loosening, narrowing, new exception, or precision change.
- [ ] Each key term has a single definition across all sections.
- [ ] Every ambiguity is either confirmed by the user or declared as the default, and it is applied consistently.
- [ ] Unrequested additions appear only as optional suggestions.
- [ ] Runtime-injection limits are declared, and the injection-side change is specified.
- [ ] The attribution table has at least one evidenced row, or explicitly records that no failure signal was given.
- [ ] Every acceptance case has both a baseline and an after value; no row is blank.
- [ ] No case is marked `regressed`; every `improved` has a baseline of `fail` or `partial`.
- [ ] The rollback path exists and is an absolute path to the pre-change file.
- [ ] Sealed cases were run last, once, and the self-grading limitation is stated.
- [ ] Summary wording, such as "all preserved" or "only enhanced", matches the ledger exactly.

If any box is unchecked, do not save or deliver.

## 7. Delivery template (compact)

1. Rewritten prompt, or its file path.
2. Failure attribution table (section 2) — what was actually wrong.
3. Change ledger (section 4).
4. Regression table (section 5) — baseline vs after, per case, with marks.
5. Hit table: each U-item and each user hard condition → `met / partial / not met / needs confirmation / pending verification`. Use `met` only for structural facts you can check in the text. Effect claims like accuracy or completeness stay `pending verification` until tested.
6. Rollback: the absolute backup path, and one line on how to restore.
7. Assumptions and open questions.
8. Optional suggestions, not applied.
9. Verification: 2–4 test inputs (normal, edge, conflict). For each, give the observable expected behavior, including at least one check per multi-object C-item.
10. Uncertainty statement. Example: "Designed to address X; not yet validated by execution."
