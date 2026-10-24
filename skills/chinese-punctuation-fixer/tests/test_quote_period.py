# -*- coding: utf-8 -*-
"""引号内句末标点规则（P1）回归测试。

用法： python tests/test_quote_period.py

断言三类：
  A. 干净文本零改动（句号已在引号内 / 引语作句子成分 / 局部引用）
  B. 病态文本 → 期望结果（句号跑到引号外，须搬回）
  C. 反向可疑情形只报告、不修改
再加幂等性断言。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

import punct_rules as rules  # noqa: E402

CLEAN = [
    "他说：“我走了。”",
    "“尾数是17，老师。”陈惊鸿恭敬地回答。",
    "“别闹，”陈惊鸿抓住她的手，“我在做饭。”",
    "他按下了“添加到通讯录”的按钮。",
    "他说的“我走了”是气话。",
    "他问：“几点？”",
    "父亲说：“人这一辈子，守得住一个铺子，就算没白活。”",
    "“外“内”外”",
    "“我不去。”",
    "她念了一句“床前明月光”，又低下头。",
]

FIX = [
    # 句号跑到引号外
    ("他说：“我走了”。", "他说：“我走了。”"),
    ("“我走了”。", "“我走了。”"),
    ("“我走了”？", "“我走了？”"),
    ("“我走了”！", "“我走了！”"),
    # 行尾：句号在引号外
    ("“别闹，”他说，“我在做饭”。", "“别闹，”他说，“我在做饭。”"),
    # 引号内已有句末标点，外面又重复一个
    ("他说：“我走了！”。", "他说：“我走了！”"),
    ("“我……”。", "“我……”"),
    # 冒号引出
    ("她低声道：“明天见”。", "她低声道：“明天见。”"),
]

# 只报告、不修改
SUSPECT_ONLY = [
    "他说的“我走了。”是气话。",
]


def main():
    bad = 0

    # A. 干净文本零改动
    for s in CLEAN:
        got, n = rules.fix_quote_period(s)
        if got != s or n:
            bad += 1
            print(f"[干净文本被改] {s}\n            → {got}")

    # B. 病态文本 → 期望
    for src, want in FIX:
        got, n = rules.fix_quote_period(src)
        if got != want:
            bad += 1
            print(f"[期望不符] {src}\n        期望 {want}\n        实际 {got}")

    # C. 反向可疑：文本不变，且能报出来
    for s in SUSPECT_ONLY:
        got, n = rules.fix_quote_period(s)
        if got != s:
            bad += 1
            print(f"[反向可疑不应被改] {s} → {got}")
        found = rules.find_quote_period_suspects(s)
        if not found:
            bad += 1
            print(f"[反向可疑应被报告但没报] {s}")

    # 干净文本不应被报成可疑
    for s in CLEAN:
        if rules.find_quote_period_suspects(s):
            bad += 1
            print(f"[误报可疑] {s}")

    # D. 幂等
    for src, _ in FIX:
        once, _ = rules.fix_quote_period(src)
        twice, n2 = rules.fix_quote_period(once)
        if n2 or twice != once:
            bad += 1
            print(f"[不幂等] {once} → {twice}")

    total = len(CLEAN) * 2 + len(FIX) * 2 + len(SUSPECT_ONLY) * 2
    print(f"\n{'全部通过' if not bad else '存在失败'}：{total - bad}/{total}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
