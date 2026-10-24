#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
中文小说/文本标点修复大师 —— 主流水线

一站式修复 txt 小说/文本的标点符号问题：
  1. 特殊符号规范化：省略号 → ……，破折号 → ——，波浪线 → ～
  2. 重复标点合并：。。 ，， ：： → 单个（!! ?? 可选）
  3. 全角字母数字 → 半角：ＡＢＣ１２３ → ABC123
  4. 英文直引号 → 中文弯引号："..." → "..."（撇号智能识别）
  5. 半角标点 → 全角（中文语境感知，保护小数/时间/URL/纯英文）
  6. 引号综合处理（不动点循环，迭代到零改动）：
     a. 行首标点禁则：续行合并（上下行明显是一句话的换行错位）、行首句号删除
     b. 引号配对修复：开闭颠倒自动纠正、漏写补齐、合法嵌套保护
     c. 单引号层级提升：双引号外层的单引号（当对话/着重引号用）→ 双引号，
        双引号内的嵌套单引号合法保留（GB/T 15834-2011 外双内单）
     d. 空引号对修复：清理 “”（双引号之间没有内容）——包裹空对、
        行首空对、倒置对话对、短强调倒置对、行尾残骸五类
     e. 跨行倒置对话修复：行N末尾 ”（倒置开引号）+ 行N+1首个 “
        （倒置闭引号）→ 翻正并合并
     f. 断链引号修复：倒置强调对 “X“ → “X”、行首叠引 ““ → “、
        漏开引号补齐、行尾漏闭补齐（预算法：只动左引号确实过多的行）
  7. 可选：直角引号转弯引号、中英文间加空格
  8. 引号内句末标点归位：把跑到引号外的 。！？ 搬回引号内
     （他说：“我走了”。 → 他说：“我走了。”）
  9. 空白清理：行尾空格、连续空行压缩
 10. 检查报告：残留行首标点（如省略号开头，有意保留）、未配对引号定位、
     引号内句末标点的反向可疑情形（只报不改）、
     成对标点（书名号/各类括号）配对情况（只报不改）

用法：
    python fix_punctuation.py 输入.txt [输出.txt] [选项]

选项：
    --check           只检查生成报告，不写文件
    --spacing         中英文之间加空格（默认关）
    --collapse-bang   合并连续感叹号/问号（默认关，小说常作风格强调）
    --trad-quotes     直角引号「」转弯引号（默认关）
    --no-ellipsis     关闭省略号规范化
    --no-dash         关闭破折号规范化
    --no-tilde        关闭波浪线规范化
    --no-repeat       关闭重复标点合并
    --no-alnum        关闭全角字母数字转半角
    --no-squote       关闭直引号转换
    --no-punct        关闭半角标点转全角
    --no-balance      关闭引号配对修复
    --no-promote      关闭单引号层级提升（外层单引号→双引号）
    --no-empty        关闭空引号对清理（“”→ 修复）
    --no-crossline    关闭跨行倒置对话修复
    --no-dangling     关闭断链引号修复（倒置强调对/行首叠引/漏开/漏闭）
    --no-quote-period 关闭引号内句末标点归位（”。→ 。”）
    --no-linehead     关闭行首标点禁则修复（续行合并/行首句号删除）
    --no-cleanup      关闭空白清理

幂等：对同一文件重复执行，第二次起修改数为 0。
"""

import argparse
import os
import sys

import punct_rules as rules
from fix_quotes import fix_text as fix_quote_balance


# ------------------------------------------------------------------
# 流水线
# ------------------------------------------------------------------

def run_pipeline(text, opt):
    """按顺序执行全部规则，返回 (新文本, 报告dict)。"""
    report = {}

    def step(key, fn, *args):
        nonlocal text
        text, n = fn(text, *args) if args else fn(text)
        report[key] = n
        return n

    # 1. 直角引号（可选，需在直引号转换前）
    if opt.trad_quotes:
        step("trad_quotes", rules.trad_quotes_to_curly)

    # 2. 特殊符号（省略号须在半角句点转换之前）
    if not opt.no_ellipsis:
        step("ellipsis", rules.normalize_ellipsis)
    if not opt.no_dash:
        step("dash", rules.normalize_dashes)
    if not opt.no_tilde:
        step("tilde", rules.normalize_tildes)

    # 3. 重复标点
    if not opt.no_repeat:
        step("repeat", rules.collapse_repeats, opt.collapse_bang)

    # 4. 全角字母数字
    if not opt.no_alnum:
        step("fullwidth_alnum", rules.fullwidth_alnum_to_half)

    # 5. 直引号 → 中文弯引号（先成对后单个）
    if not opt.no_squote:
        text, n_dq, n_sq, n_apos = rules.convert_straight_quotes(text)
        report["straight_dquote"] = n_dq
        report["straight_squote"] = n_sq
        report["apostrophe"] = n_apos

    # 6. 半角标点 → 全角（中文语境）
    if not opt.no_punct:
        step("ascii_punct", rules.convert_ascii_punct)

    # 7. 引号综合处理：不动点循环
    #    行首禁则合并 → 配对修复 → 单引号层级提升 → 空引号对修复
    # 四者互相影响：提升会把单引号改写成双引号、改变布局，可能让原本
    # 判定为嵌套的单引号暴露为外层，也可能产生新的行首闭引号续行；
    # 合并会改变行的结构，影响逐行配对的结果；配对补引号会在行尾
    # 生成 “” 空对，必须再清掉。因此循环到一次完整迭代零改动——
    # 最终状态与步骤顺序无关，重复执行幂等。
    odd_nested_snippets = []
    if not (opt.no_balance and opt.no_promote and opt.no_linehead
            and opt.no_empty and opt.no_crossline and opt.no_dangling):
        for _ in range(10):
            iter_changed = False
            iter_before = text

            # 7a. 行首标点禁则：续行合并 + 行首句号删除。
            # 必须先合并再配对：闭引号开头的续行若先做配对重排，
            # 行首闭引号会被交替规则错改成开引号，续行就再也合不回去
            if not opt.no_linehead:
                text, nm, nd = rules.fix_line_start_punct(text)
                report["linehead_merged"] = report.get("linehead_merged", 0) + nm
                report["linehead_deleted"] = report.get("linehead_deleted", 0) + nd
                iter_changed = iter_changed or bool(nm or nd)

            # 7b0. 断链引号修复（必须在配对修复之前）：先把”倒置强调对、
            # 行首叠引、漏开引号、行尾漏闭”这些结构性断裂修掉。
            # 反之先做交替重排，重排会被这些断裂带偏，放弃整行或把正常
            # 开引号错翻（《冰山女教师》实测：先重排会残留 242 行不平衡）
            if not opt.no_dangling:
                text, n_dg = rules.fix_dangling_quotes(text)
                report["dangling_quote"] = report.get("dangling_quote", 0) + n_dg
                iter_changed = iter_changed or bool(n_dg)

            # 7b. 引号配对修复（颠倒/漏写/嵌套保护）
            if not opt.no_balance:
                in_lines = text.split("\n")
                text, qs = fix_quote_balance(text)
                for k in ("quote_flipped", "quote_added", "quote_removed"):
                    report[k] = report.get(k, 0) + qs.get(k, 0)
                for ln_no in qs.get("quote_odd_nested", []):
                    if 1 <= ln_no <= len(in_lines):
                        odd_nested_snippets.append(in_lines[ln_no - 1].strip()[:40])
                iter_changed = iter_changed or bool(
                    qs["quote_flipped"] or qs["quote_added"] or qs["quote_removed"]
                )

            # 7c. 单引号层级提升：双引号外层的单引号（被当作对话/着重
            # 引号用）提升为双引号；双引号内的嵌套单引号合法，保留
            if not opt.no_promote:
                text, n_pro, n_nested = rules.promote_single_quotes(text)
                report["squote_promote"] = report.get("squote_promote", 0) + n_pro
                report["squote_nested_kept"] = n_nested
                iter_changed = iter_changed or bool(n_pro)

            # 7d. 空引号对修复：清理 “”（双引号之间没有内容）。
            # 必须在配对修复之后——配对补引号会在行尾生成新的空对；
            # 清理后行可能变奇数，下一轮配对修复的守卫会保证不再振荡
            if not opt.no_empty:
                text, n_empty = rules.fix_empty_quote_pairs(text)
                report["empty_pair"] = report.get("empty_pair", 0) + n_empty
                iter_changed = iter_changed or bool(n_empty)

            # 7e. 跨行倒置对话：行N末尾 ”（倒置开引号）+ 行N+1首个 “
            # （倒置闭引号）→ 翻正并合并。必须在配对修复之后，且把对话
            # 合并成行内引号对，避免配对步把行N末尾孤立开引号补成 “”
            if not opt.no_crossline:
                text, n_cr = rules.fix_crossline_inverted_quotes(text)
                report["crossline_quote"] = report.get("crossline_quote", 0) + n_cr
                iter_changed = iter_changed or bool(n_cr)

            if not iter_changed:
                break
            if text == iter_before:
                # 本轮多个步骤互相抵消（如 配对补引号 ↔ 空对删除），
                # 净零改动即已稳定，退出（否则空转满 10 轮）
                break

    # 奇数嵌套样貌行的最终行号（循环中可能发生合并，按内容回查行号）
    final_lines = text.split("\n")
    odd_nested_final = []
    for snip in dict.fromkeys(odd_nested_snippets):
        for idx, fl in enumerate(final_lines, 1):
            if snip and snip in fl:
                odd_nested_final.append(idx)
                break
    report["quote_odd_nested"] = odd_nested_final

    # 8. 引号内外句末标点（P1）：把跑到引号外的 。！？ 搬回引号内。
    #    必须放在不动点循环之后：循环内的补闭约定（E3/E4 附带补闭、
    #    D5/D7）一律把 ” 补在句读之后，与本规则方向相同，故不冲突；
    #    本规则只搬标点不增删引号，不改变平衡，不会破坏循环的收敛结果。
    #    反向搬移（。” → ”。）会与上述补闭约定振荡，因此不做，只报告。
    if not opt.no_quote_period:
        step("quote_period", rules.fix_quote_period)

    # 9. 中英文空格（可选）
    if opt.spacing:
        step("spacing", rules.add_cjk_latin_spacing)

    # 10. 空白清理
    if not opt.no_cleanup:
        step("whitespace", rules.cleanup_whitespace)

    # 11. 检查类报告（不修改）
    report["linehead_punct"] = rules.find_linehead_punct(text)
    un_l, un_r = rules.count_unbalanced_quotes(text)
    report["unclosed_left_lines"] = un_l
    report["extra_right_lines"] = un_r
    report["quote_period_suspects"] = rules.find_quote_period_suspects(text)
    report["paired_symbols"] = rules.check_paired_symbols(text)

    return text, report


# ------------------------------------------------------------------
# 文件读写
# ------------------------------------------------------------------

def read_text(path):
    """读取文本，保留 BOM 与换行符信息。"""
    with open(path, "rb") as f:
        raw = f.read()
    had_bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    newline = "\r\n" if "\r\n" in text else "\n"
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text, had_bom, newline


def write_text(path, text, had_bom, newline):
    out = text.replace("\n", newline) if newline != "\n" else text
    with open(path, "wb") as f:
        if had_bom:
            f.write(b"\xef\xbb\xbf")
        f.write(out.encode("utf-8"))


# ------------------------------------------------------------------
# 报告
# ------------------------------------------------------------------

def print_report(report, check_only, out_path, orig_text, new_text):
    L = "\u201c"
    R = "\u201d"
    print("=" * 46)
    print("中文标点修复报告" + ("（仅检查，未修改）" if check_only else ""))
    print("=" * 46)

    print("[修改统计]")
    labels = [
        ("ellipsis", "省略号规范化 → ……"),
        ("dash", "破折号规范化 → ——"),
        ("tilde", "波浪线规范化 → ～"),
        ("repeat", "重复标点合并"),
        ("fullwidth_alnum", "全角字母数字 → 半角"),
        ("straight_dquote", "英文直双引号 → 中文"),
        ("straight_squote", "英文直单引号 → 中文"),
        ("apostrophe", "撇号 → 弯撇号 ’"),
        ("ascii_punct", "半角标点 → 全角"),
        ("quote_flipped", "引号开闭方向纠正"),
        ("quote_added", "引号漏写补齐"),
        ("quote_removed", "多余引号删除"),
        ("squote_promote", "单引号层级提升 → 双引号"),
        ("empty_pair", "空引号对清理（“”→ 修复）"),
        ("crossline_quote", "跨行倒置对话修复"),
        ("dangling_quote", "断链引号修复（倒置强调/叠引/漏开漏闭）"),
        ("quote_period", "引号内句末标点归位（”。→ 。”）"),
        ("linehead_merged", "行首标点续行合并"),
        ("linehead_deleted", "行首句号删除"),
        ("trad_quotes", "直角引号 → 弯引号"),
        ("spacing", "中英文间补空格"),
        ("whitespace", "空白清理（行尾/空行）"),
    ]
    total = 0
    for key, label in labels:
        if key in report:
            n = report[key]
            total += n
            print(f"  {label:<24} {n:>6} 处")
    print(f"  {'合计':<24} {total:>6} 处")

    ol = orig_text.count(L)
    orr = orig_text.count(R)
    nl = new_text.count(L)
    nr = new_text.count(R)
    print()
    print("[引号平衡]")
    print(f"  原文：左引号 {ol} / 右引号 {orr}（差 {ol - orr}）")
    print(f"  现在：左引号 {nl} / 右引号 {nr}（差 {nl - nr}）")
    nested = report.get("squote_nested_kept")
    if nested is not None:
        print(f"  嵌套单引号（双引号内合法，保留）：{nested} 个")

    lh = report.get("linehead_punct") or []
    un_l = report.get("unclosed_left_lines") or []
    un_r = report.get("extra_right_lines") or []
    odd_nested = report.get("quote_odd_nested") or []
    qp = report.get("quote_period_suspects") or []
    ps = report.get("paired_symbols") or {}
    if lh or un_l or un_r or odd_nested:
        print()
        print("[需人工关注]")
        if un_l:
            print(f"  未闭合左引号（疑似对话没结尾）：{len(un_l)} 处，行号 {un_l[:20]}")
        if un_r:
            print(f"  多余右引号（疑似对话缺开头）：{len(un_r)} 处，行号 {un_r[:20]}")
        if odd_nested:
            print(f"  疑似复杂嵌套行（引号奇数、已自动平衡，建议人工复核）："
                  f"{len(odd_nested)} 处，行号 {odd_nested[:20]}")
        if lh:
            print(f"  行首标点禁则：{len(lh)} 处，行号 {[x[0] for x in lh[:20]]}")
            for ln, ctx in lh[:5]:
                print(f"      行{ln}: {ctx}")
    else:
        if not (qp or ps):
            print()
            print("[需人工关注] 无 —— 引号全部配对，无行首标点禁则")

    # 引号内句末标点：只报告的反向可疑情形（引语疑作句子成分）
    if qp:
        print()
        print("[引号内句末标点 · 仅报告，未修改]")
        print(f"  引号内有句末标点、但引语疑作句子成分：{len(qp)} 处")
        print("  （`他说的“我走了。”是气话。` 这类，句号该在引号外；"
              "改动等于删内容，故交人工）")
        for ln, ctx in qp[:8]:
            print(f"      行{ln}: {ctx}")
        if len(qp) > 8:
            print(f"      …… 其余 {len(qp) - 8} 处见上方行号")
        print(f"  行号 {[x[0] for x in qp[:30]]}")

    # 成对标点（书名号/各类括号）：只报告
    if ps:
        print()
        print("[成对标点检查 · 仅报告，未修改]")
        for name, d in ps.items():
            print(f"  {name}：左 {d['left']} / 右 {d['right']}"
                  f"（差 {d['left'] - d['right']}）")
            if d["unclosed_left"]:
                print(f"      未闭合左符号：{len(d['unclosed_left'])} 处，"
                      f"行号 {d['unclosed_left'][:20]}")
            if d["extra_right"]:
                print(f"      多余右符号：{len(d['extra_right'])} 处，"
                      f"行号 {d['extra_right'][:20]}")

    if not check_only:
        print()
        print(f"输出文件：{out_path}")


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="中文小说/文本标点修复大师",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("input", help="输入 txt 文件")
    ap.add_argument("output", nargs="?", default=None, help="输出文件（默认：原名_已修正标点.txt）")
    ap.add_argument("--check", action="store_true", help="只检查生成报告，不写文件")
    ap.add_argument("--spacing", action="store_true", help="中英文之间加空格（默认关）")
    ap.add_argument("--collapse-bang", action="store_true", help="合并连续感叹号/问号（默认关）")
    ap.add_argument("--trad-quotes", action="store_true", help="直角引号「」转弯引号（默认关）")
    ap.add_argument("--no-ellipsis", action="store_true")
    ap.add_argument("--no-dash", action="store_true")
    ap.add_argument("--no-tilde", action="store_true")
    ap.add_argument("--no-repeat", action="store_true")
    ap.add_argument("--no-alnum", action="store_true")
    ap.add_argument("--no-squote", action="store_true")
    ap.add_argument("--no-punct", action="store_true")
    ap.add_argument("--no-balance", action="store_true")
    ap.add_argument("--no-promote", action="store_true", help="关闭单引号层级提升（外层单引号→双引号）")
    ap.add_argument("--no-empty", action="store_true", help="关闭空引号对清理（“”→ 修复）")
    ap.add_argument("--no-crossline", action="store_true", help="关闭跨行倒置对话修复")
    ap.add_argument("--no-dangling", action="store_true", help="关闭断链引号修复（倒置强调对/行首叠引/漏开/漏闭）")
    ap.add_argument("--no-quote-period", action="store_true", help="关闭引号内句末标点归位（”。→ 。”）")
    ap.add_argument("--no-linehead", action="store_true", help="关闭行首标点禁则修复（续行合并/行首句号删除）")
    ap.add_argument("--no-cleanup", action="store_true")
    opt = ap.parse_args()

    if not os.path.exists(opt.input):
        print(f"错误：文件不存在 {opt.input}")
        sys.exit(1)

    if opt.output is None:
        base, ext = os.path.splitext(opt.input)
        opt.output = base + "_已修正标点" + (ext or ".txt")

    orig_text, had_bom, newline = read_text(opt.input)
    new_text, report = run_pipeline(orig_text, opt)

    if not opt.check:
        write_text(opt.output, new_text, had_bom, newline)

    print_report(report, opt.check, opt.output, orig_text, new_text)


if __name__ == "__main__":
    main()
