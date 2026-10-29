#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""tokens.py —— 记忆压缩的"外部尺子"

解决什么问题：压缩后靠人凭记忆列"必须保住的令牌"，漏掉什么就查不到什么（自己批改自己）。
本脚本从**旧文件**里程序化抽取令牌，再逐个到新文件里查，清单不依赖记忆。

两个检查：
  1 令牌：数字/金额、版本号、提交号、盘符路径、反引号标识符、URL —— 旧有新无即报缺失
  2 不确定标记：旧文件里的"可能/大概/估计/应该/似乎/待验证/待确认"，新文件少了就报警
     （压缩最常见的隐性损伤：把"可能是 X"写成"是 X"，关键词都在但确定性被拔高）

用法：
  python tokens.py extract 旧.md                   只看会抽哪些令牌
  python tokens.py check   旧.md 新.md             查缺失（退出码 1 = 有缺失）
  python tokens.py check   旧.md 新.md --allow 1902941,12   允许消失的令牌（如已过时的提交号）
"""
from __future__ import annotations

import argparse
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HEDGE = ("可能", "大概", "估计", "应该", "似乎", "待验证", "待确认", "未验证", "推测")

PATTERNS = [
    re.compile(r"[A-Za-z]:[\\/][^\s`）)，。；]+"),          # 盘符路径
    re.compile(r"~[/\\]\.workbuddy[^\s`）)，。；]*"),        # home 路径
    re.compile(r"https?://[^\s`）)，。；]+"),               # URL
    re.compile(r"\b\d+\.\d+\.\d+\b"),                       # 版本号 x.y.z
    re.compile(r"\b[0-9a-f]{7,40}\b"),                      # 提交号
    re.compile(r"`[^`\n]{2,40}`"),                          # 反引号标识符
    re.compile(r"[¥￥]?\d[\d,]*\.?\d*\s*(?:万元|元|KB|MB|GB|个|条|份|字符|行)?"),
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),                   # 日期
]

TRIVIAL = {"1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "0",
           "20", "30", "50", "100", "300", "1000", "3000"}


def tokens(text):
    out = set()
    for p in PATTERNS:
        for m in p.findall(text):
            t = m.strip().strip("`")
            if not t or t in TRIVIAL or len(t) < 2:
                continue
            # 噪音过滤：纯数字且无单位、数值 < 100 的（如 "16" "05" "4 行" 这类行内小数字）
            digits = re.sub(r"[^0-9.]", "", t)
            has_unit = bool(re.search(r"[\u4e00-\u9fa5A-Za-z%]", t)) and not re.fullmatch(r"\d+", digits or "x")
            try:
                val = float(digits) if digits else None
            except ValueError:
                val = None
            if val is not None and val < 10:
                continue
            if val is not None and val < 100 and not re.search(r"(元|KB|MB|GB|字符|条|份|个)", t):
                continue
            out.add(t)
    return out


def hedges(text):
    out = {}
    for h in HEDGE:
        n = text.count(h)
        if n:
            out[h] = n
    return out


def main():
    ap = argparse.ArgumentParser(description="记忆压缩的外部核验尺子")
    ap.add_argument("mode", choices=["extract", "check"])
    ap.add_argument("old")
    ap.add_argument("new", nargs="?")
    ap.add_argument("--allow", default="", help="允许消失的令牌，逗号分隔")
    a = ap.parse_args()

    old = open(a.old, encoding="utf-8").read()
    toks = tokens(old)

    if a.mode == "extract":
        print("从 %s 抽出 %d 个令牌：" % (a.old, len(toks)))
        for t in sorted(toks):
            print("  " + t)
        h = hedges(old)
        if h:
            print("\n不确定标记：%s" % h)
        return 0

    if not a.new:
        print("check 需要两个文件：旧 新")
        return 2
    new = open(a.new, encoding="utf-8").read()
    allow = {x.strip() for x in a.allow.split(",") if x.strip()}

    missing = sorted(t for t in toks if t not in new and t not in allow)
    print("== 令牌核验 ==")
    print("  旧文件 %d 个令牌 → 新文件缺失 %d 个" % (len(toks), len(missing)))
    for t in missing:
        print("  [缺] %s" % t)
    if allow:
        print("  已豁免: %s" % ", ".join(sorted(allow)))

    ho, hn = hedges(old), hedges(new)
    print("\n== 不确定标记核验 ==")
    warn = 0
    for h, n in sorted(ho.items()):
        m = hn.get(h, 0)
        flag = "" if m >= n else "  ← 减少，需人工确认是否被拔高成定论"
        if m < n:
            warn += 1
        print("  %-4s 旧 %d → 新 %d%s" % (h, n, m, flag))
    if not ho:
        print("  旧文件无不确定标记")

    print("\n结论：令牌缺失 %d，标记减少 %d 处%s" % (
        len(missing), warn, "" if not (missing or warn) else "　→ 逐条人工确认后再定稿"))
    return 1 if (missing or warn) else 0


if __name__ == "__main__":
    sys.exit(main())
