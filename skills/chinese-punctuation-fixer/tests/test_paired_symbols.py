# -*- coding: utf-8 -*-
"""成对标点检查（P2：书名号 / 各类括号）回归测试。

用法： python tests/test_paired_symbols.py

本规则只报告、不修改，因此断言重点在「该报的报、不该报的不报」：
  A. 干净文本 → 返回空 dict
  B. 跨行配对（合法排版）→ 不报
  C. 缺失 / 多余 / 逆序 → 必须报出正确行号
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

import punct_rules as rules  # noqa: E402

CLEAN = [
    "他读了《红楼梦》和《三国演义》。",
    "他读了《红楼梦》，又在（注：此处存疑）处停笔。",
    "书名号里套书名号：《〈呐喊〉自序》。",
    "她说：「你走吧。」",
    "参见《论语·学而》〔宋刻本〕。",
    "他用「引号」标注，并用【重点】提示。",
]

# 跨行配对：一行开、几行后闭，属合法排版
CROSS_LINE = [
    "这是一句跨行的话（需要\n两三行才说完）。",
    "他翻开《红楼梦\n（校注本）》，看了很久。",
]

BAD = [
    # (文本, 期望出现的符号名, 期望 unclosed_left 行号, 期望 extra_right 行号)
    ("他读了《红楼梦，就睡了。", "书名号", [1], []),
    ("他读了红楼梦》，就睡了。", "书名号", [], [1]),
    ("他读了《红楼梦》》，就睡了。", "书名号", [], [1]),
    ("第一行《红楼梦\n第二行还开着。", "书名号", [1], []),
    ("他说（你走吧，就走了。", "圆括号", [1], []),
    ("她说「你走吧，就走了。", "直角引号", [1], []),
]


def main():
    bad = 0
    total = 0

    for s in CLEAN + CROSS_LINE:
        total += 1
        res = rules.check_paired_symbols(s)
        if res:
            bad += 1
            print(f"[误报] {s!r}\n      → {res}")

    for s, name, want_left, want_right in BAD:
        total += 1
        res = rules.check_paired_symbols(s)
        if name not in res:
            bad += 1
            print(f"[漏报 {name}] {s!r}\n      → {res}")
            continue
        d = res[name]
        if d["unclosed_left"] != want_left or d["extra_right"] != want_right:
            bad += 1
            print(f"[行号不符 {name}] {s!r}")
            print(f"      期望 unclosed={want_left} extra={want_right}")
            print(f"      实际 unclosed={d['unclosed_left']} "
                  f"extra={d['extra_right']}")

    # 只读断言：调用前后文本不变
    for s in CLEAN + CROSS_LINE + [b[0] for b in BAD]:
        total += 1
        before = s
        rules.check_paired_symbols(s)
        if s != before:
            bad += 1
            print(f"[检查函数修改了入参] {s!r}")

    print(f"\n{'全部通过' if not bad else '存在失败'}：{total - bad}/{total}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
