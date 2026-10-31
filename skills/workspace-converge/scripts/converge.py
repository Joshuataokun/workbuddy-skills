#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""converge.py —— 收敛的五项核验，一条命令出结论

为什么要有它：五项核验原本是四条命令（tokens.py / 路径 exists / len / wc -l）靠人肉跑，
写成文字就会漏项。可验证的逻辑必须交给代码——代码是确定性的，语言解读不是。

用法：
  python converge.py verify 旧.md 新.md
  python converge.py verify 旧.md 新.md --max-chars 2600 --max-lines 70
  python converge.py verify 旧.md 新.md --allow 1902941,2026-10-29
  python converge.py snapshot <要备份的目录或文件> [--label 20261030]

退出码：0 全部通过；1 有失败。失败即回滚（技能第 10 条）。
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tokens import tokens, hedges  # noqa: E402

PATH_RE = re.compile(r"(?:[A-Za-z]:[\\/]|~/)[^\s`）)，。；、]+")


def check_tokens(old, new, allow):
    toks = tokens(old)
    missing = sorted(t for t in toks if t not in new and t not in allow)
    return (not missing), "%d 个令牌，缺失 %d%s" % (
        len(toks), len(missing),
        ("：" + "、".join(missing[:6]) + ("…" if len(missing) > 6 else "")) if missing else "")


def check_hedges(old, new):
    ho, hn = hedges(old), hedges(new)
    drops = [(h, n, hn.get(h, 0)) for h, n in sorted(ho.items()) if hn.get(h, 0) < n]
    return (not drops), ("不确定标记 %d 处，减少 %d 处%s" % (
        sum(ho.values()), len(drops),
        ("：" + "、".join("%s %d→%d" % d for d in drops)) if drops else ""))


def check_paths(new):
    cands = sorted({c.rstrip("\\/，。；、") for c in PATH_RE.findall(new)})
    bad = [c for c in cands if "*" not in c and "…" not in c and not os.path.exists(c)]
    return (not bad), "%d 处路径，失效 %d%s" % (
        len(cands), len(bad), ("：" + "、".join(bad[:4])) if bad else "")


def main():
    ap = argparse.ArgumentParser(description="收敛五项核验 / 快照")
    sub = ap.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("verify", help="五项核验：令牌/推测标记/路径/字符/行数")
    v.add_argument("old")
    v.add_argument("new")
    v.add_argument("--max-chars", type=int, default=3000)
    v.add_argument("--max-lines", type=int, default=70)
    v.add_argument("--allow", default="", help="允许消失的令牌，逗号分隔")

    s = sub.add_parser("snapshot", help="快照并做 md5 校验（回滚点）")
    s.add_argument("src")
    s.add_argument("--dest-root", default=os.path.expanduser("~/.workbuddy/backups"))
    s.add_argument("--label", default=time.strftime("%Y%m%d-%H%M%S"))

    a = ap.parse_args()

    if a.cmd == "snapshot":
        if not os.path.exists(a.src):
            print("FAIL 源不存在: %s" % a.src)
            return 1
        dst = os.path.join(a.dest_root, "%s-%s" % (os.path.basename(a.src.rstrip("\\/")), a.label))
        os.makedirs(a.dest_root, exist_ok=True)
        if os.path.isdir(a.src):
            shutil.copytree(a.src, dst, dirs_exist_ok=True)
        else:
            os.makedirs(dst, exist_ok=True)
            shutil.copy2(a.src, os.path.join(dst, os.path.basename(a.src)))
        # md5 校验：逐文件比对，证明快照可恢复
        n, bad = 0, 0
        if os.path.isdir(a.src):
            for root, _, files in os.walk(a.src):
                for f in files:
                    sp = os.path.join(root, f)
                    rel = os.path.relpath(sp, a.src)
                    dp = os.path.join(dst, rel)
                    n += 1
                    if not os.path.isfile(dp) or \
                            hashlib.md5(open(sp, "rb").read()).hexdigest() != \
                            hashlib.md5(open(dp, "rb").read()).hexdigest():
                        bad += 1
        else:
            n = 1
            bad = 0 if hashlib.md5(open(a.src, "rb").read()).hexdigest() == \
                hashlib.md5(open(os.path.join(dst, os.path.basename(a.src)), "rb").read()).hexdigest() else 1
        print("快照: %s" % dst)
        print("md5 校验: %d 个文件，不一致 %d" % (n, bad))
        return 0 if bad == 0 else 1

    old = open(a.old, encoding="utf-8").read()
    new = open(a.new, encoding="utf-8").read()
    allow = {x.strip() for x in a.allow.split(",") if x.strip()}
    chars, lines = len(new), len(new.splitlines())

    results = [
        ("令牌", *check_tokens(old, new, allow)),
        ("推测标记", *check_hedges(old, new)),
        ("路径", *check_paths(new)),
        ("字符", chars <= a.max_chars, "%d / %d" % (chars, a.max_chars)),
        ("行数", lines <= a.max_lines, "%d / %d" % (lines, a.max_lines)),
    ]

    print("== 收敛核验 ==")
    print("  旧 %d 字符 / %d 行 → 新 %d 字符 / %d 行\n" % (
        len(old), len(old.splitlines()), chars, lines))
    fails = 0
    for name, ok, detail in results:
        if not ok:
            fails += 1
        print("  %s  %-6s %s" % ("PASS" if ok else "FAIL", name, detail))

    print("\n结论：%s" % ("全部通过，可定稿" if fails == 0 else
                        "%d 项失败 → 回滚（技能第 10 条），或逐项说明后用 --allow 豁免" % fails))
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
