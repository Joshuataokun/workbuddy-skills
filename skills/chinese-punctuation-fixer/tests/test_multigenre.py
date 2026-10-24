# -*- coding: utf-8 -*-
"""多体裁回归测试（P4）。

用法： python tests/test_multigenre.py

目的：防止规则只对「某一本网文」过拟合。

原规则全部从《覆雨翻云》《冰山女教师》这类网文反推得到，语料单一。
本测试用三种体裁的**干净文本**跑完整流水线，断言零改动：

  1. guwen.txt    古文 / 诗词 —— 无引号对话、多分号顿号、书名号频繁
  2. xiandai.txt  现代纯文学 —— 对话＋长旁白混合、破折号插入语
  3. duihua.txt   对话密集 —— 连续对话、外双内单嵌套、引号密度极高

干净文本零改动是本 skill 的核心安全承诺（见 SKILL.md 注意事项 8）。
任何规则改动后先跑本测试，再跑 test_dangling.py。
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

import fix_punctuation as fp  # noqa: E402

CORPUS_DIR = os.path.join(HERE, "corpus")

# 零改动断言针对的键：全部属于「会修改正文」的规则
MUTATING_KEYS = [
    "ellipsis", "dash", "tilde", "repeat", "fullwidth_alnum",
    "straight_dquote", "straight_squote", "apostrophe", "ascii_punct",
    "quote_flipped", "quote_added", "quote_removed",
    "squote_promote", "empty_pair", "crossline_quote",
    "dangling_quote", "quote_period",
    "linehead_merged", "linehead_deleted", "whitespace",
    "trad_quotes", "spacing",
]


def default_opt():
    """构造一份「全默认」选项：所有规则开启、可选功能关闭。"""
    return argparse.Namespace(
        trad_quotes=False, spacing=False, collapse_bang=False,
        no_ellipsis=False, no_dash=False, no_tilde=False, no_repeat=False,
        no_alnum=False, no_squote=False, no_punct=False,
        no_balance=False, no_promote=False, no_empty=False,
        no_crossline=False, no_dangling=False, no_quote_period=False,
        no_linehead=False, no_cleanup=False,
    )


def main():
    opt = default_opt()
    names = ["guwen.txt", "xiandai.txt", "duihua.txt"]
    bad = 0
    checked = 0

    for name in names:
        path = os.path.join(CORPUS_DIR, name)
        if not os.path.exists(path):
            print(f"[缺失] {path}")
            bad += 1
            continue

        with open(path, encoding="utf-8") as f:
            src = f.read()
        if src.startswith("\ufeff"):
            src = src[1:]

        out, report = fp.run_pipeline(src, opt)
        checked += 1

        # 断言 1：输出逐字等于输入
        if out != src:
            bad += 1
            print(f"[{name}] 干净文本被改动")
            inl, outl = src.split("\n"), out.split("\n")
            for i in range(max(len(inl), len(outl))):
                a = inl[i] if i < len(inl) else "<缺行>"
                b = outl[i] if i < len(outl) else "<缺行>"
                if a != b:
                    print(f"    行{i + 1}")
                    print(f"      原 {a}")
                    print(f"      新 {b}")

        # 断言 2：所有会改正文的规则计数必须为 0
        hit = {k: report.get(k) for k in MUTATING_KEYS
               if isinstance(report.get(k), int) and report.get(k)}
        if hit:
            bad += 1
            print(f"[{name}] 规则被误触发：{hit}")

        # 断言 3：成对标点全部配对（fixture 必须自己是干净的）
        ps = report.get("paired_symbols") or {}
        if ps:
            bad += 1
            print(f"[{name}] fixture 自身成对标点不配对：{ps}")

        # 断言 4：幂等（再跑一遍零改动）
        out2, report2 = fp.run_pipeline(out, opt)
        if out2 != out:
            bad += 1
            print(f"[{name}] 二次运行不幂等")
        hit2 = {k: report2.get(k) for k in MUTATING_KEYS
                if isinstance(report2.get(k), int) and report2.get(k)}
        if hit2:
            bad += 1
            print(f"[{name}] 二次运行仍有改动：{hit2}")

    total = checked * 4
    print(f"\n{'全部通过' if not bad else '存在失败'}：{total - bad}/{total}"
          f"（{checked} 个体裁样本 × 4 项断言）")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
