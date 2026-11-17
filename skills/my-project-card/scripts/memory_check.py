#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""my-project-card · 用户级 / 空间级 MEMORY.md 预算体检与整合提案

2026-11-18 用户拍板方案 A。硬约束：
- 阈值沿用 3000 字符 / 70 行，只在超过 80% 时预警，不阻断、不自动删。
- check 只读，绝不改任何文件；apply 必须逐条给 --ids 且显式 --confirm 才写。
- 用户级 MEMORY.md 全空间共用 → 只读体检；apply --scope user 一律拒绝。
- 删前备份 + sha256 + 写变更报告；台账不是恢复源。
- 不做日志归档、不复活收敛技能 B 档压缩记忆。

参照（一手，2026-11-18 查）：Claude Code 官方 memory 文档（写后自动量、
接近上限提醒 merge or drop stale entries）；GitHub tigerless-labs/agent-memory
README（无人值守只 add/update，删除永远只是提案）；GitHub
josiahcrackle9631/memory-bank 的 context-efficiency.md（会话结束出 compression report）。

只依赖标准库。可被 pitfall_inject.py import 用 budget_status() 做轻量预警。
"""
from __future__ import annotations

import argparse
import datetime as dt
import difflib
import glob
import hashlib
import io
import os
import re
import shutil
import sys

MAX_CHARS = 3000
MAX_LINES = 70
WARN_RATIO = 0.80
SIM_THRESHOLD = 0.93
MIN_LEN = 12

# 验收时用 MEMORY_CHECK_HOME 把整个 HOME 重定向到临时目录，绝不碰真实记忆
HOME = os.path.abspath(os.environ.get("MEMORY_CHECK_HOME") or os.path.expanduser("~"))
ITEM_PREFIX = re.compile(r"^\s*(?:[-*]\s+|\d+\.\s+|>\s*)")
STALE_RE = re.compile(r"已失效|已废弃|已作废|不再使用|旧口径|已删除|不再生效")
# 只收推测性陈述，不收「不确定」「可能」这类描述规则场景的词（会误伤硬规则）
GUESS_RE = re.compile(r"大概|估计|大概率|似乎|也许|应该是|可能是|疑似")
CRED_RE = re.compile(r"(?:api[_-]?key|password|passwd|secret|token|私钥|密码)\s*[=:：]|BEGIN [A-Z ]*PRIVATE KEY", re.I)
BACKUP_REL = os.path.join(".workbuddy", "backups")
REPORT_REL = os.path.join(".workbuddy", "archive", "memory-变更报告.md")

KIND_NAME = {
    "stale": "失效标记",
    "dup": "重复条目",
    "elsewhere": "别处已有",
    "verify": "待核实",
}
KIND_ACTION = {
    "stale": "确认后删除",
    "dup": "合并或删除其一",
    "elsewhere": "留指针、删正文",
    "verify": "补来源或改【待确认】",
}
PRIORITY = ("stale", "dup", "elsewhere", "verify")


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for c in iter(lambda: f.read(65536), b""):
            h.update(c)
    return h.hexdigest()


def read(path: str) -> str:
    with io.open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def find_user_memory():
    hits = sorted(glob.glob(os.path.join(HOME, ".workbuddy", "user-*", "MEMORY.md")))
    return hits[0] if hits else None


def space_memory(workspace: str) -> str:
    return os.path.join(os.path.abspath(workspace), ".workbuddy", "memory", "MEMORY.md")


def stats(path: str):
    if not path or not os.path.isfile(path):
        return None
    text = read(path)
    chars, lines = len(text), len(text.splitlines())
    return {"path": path, "text": text, "chars": chars, "lines": lines,
            "pc": chars / MAX_CHARS, "pl": lines / MAX_LINES}


def over80(s) -> bool:
    return bool(s) and (s["pc"] >= WARN_RATIO or s["pl"] >= WARN_RATIO)


def budget_status(workspace: str | None = None):
    """给 SessionStart hook 用：只量两个数，返回 (是否预警, 一行文本)。"""
    try:
        ws = os.path.abspath(workspace or os.getcwd())
        pairs = [("用户级", stats(find_user_memory())), ("空间级", stats(space_memory(ws)))]
        hot = [(n, s) for n, s in pairs if over80(s)]
        if not hot:
            return False, ""
        desc = "、".join("%s %d/%d 字符" % (n, s["chars"], MAX_CHARS) for n, s in hot)
        return True, ("⚠ 记忆预算：%s，已超 %d%%。" % (desc, int(WARN_RATIO * 100))
                      + "跑 `memory_check.py check` 看待整合清单（只出提案，不自动删）。")
    except Exception:
        return False, ""


def norm(ln: str) -> str:
    s = ITEM_PREFIX.sub("", ln.strip())
    s = s.replace("`", "").replace("**", "")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def is_item(ln: str) -> bool:
    if not ITEM_PREFIX.match(ln):
        return False
    s = ln.strip().lstrip("-*> ").strip()
    return len(s) >= 6


def similar(a: str, b: str) -> bool:
    if len(a) < MIN_LEN or len(b) < MIN_LEN:
        return False
    if a == b:
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= SIM_THRESHOLD


def collect_lines(text: str):
    return [(i, ln) for i, ln in enumerate(text.splitlines(), 1) if is_item(ln)]


def candidates(workspace: str):
    """只读扫描，返回带编号的候选。一个条目只出一条，理由可叠加。"""
    ws = os.path.abspath(workspace)
    up, wp = find_user_memory(), space_memory(ws)
    su, sw = stats(up), stats(wp)
    sources = []
    for scope, s in (("user", su), ("workspace", sw)):
        if s:
            sources.append((scope, s["path"], collect_lines(s["text"])))

    # 「别处已有」的参照：另一份 MEMORY.md + 空间当天日志 + 卡片主卡
    refs = []
    for scope, path, _ in sources:
        refs.append((scope, path, read(path)))
    for p in sorted(glob.glob(os.path.join(ws, ".workbuddy", "memory", "20*.md"))):
        if os.path.abspath(p) != os.path.abspath(wp):
            try:
                refs.append(("log", p, read(p)))
            except Exception:
                pass
    for p in sorted(glob.glob(os.path.join(HOME, ".workbuddy", "cards", "*", "context-card.md"))):
        try:
            refs.append(("card", p, read(p)))
        except Exception:
            pass

    out, n = [], 0
    for scope, path, items in sources:
        seen = []
        for lineno, ln in items:
            body = norm(ln)
            if len(body) < MIN_LEN:
                continue
            kinds = []
            if STALE_RE.search(body):
                kinds.append("stale")
            if any(similar(body, prev) for prev in seen):
                kinds.append("dup")
            if any(tag != scope and body in txt for tag, _, txt in refs):
                kinds.append("elsewhere")
            if GUESS_RE.search(body) or CRED_RE.search(body):
                kinds.append("verify")
            seen.append(body)
            if not kinds:
                continue
            n += 1
            kind = next(k for k in PRIORITY if k in kinds)
            out.append({"id": n, "scope": scope, "path": path, "lineno": lineno,
                        "kind": kind, "kinds": kinds, "text": body[:110],
                        "raw": ln, "reason": "／".join(KIND_NAME[k] for k in kinds)})
    return (su, sw), out


def print_check(workspace: str) -> int:
    (su, sw), cands = candidates(workspace)
    print("=== 记忆预算（只读，不改文件）===")
    for name, s in (("用户级", su), ("空间级", sw)):
        if not s:
            print("  %s  未找到 MEMORY.md" % name)
            continue
        flag = "⚠ 超 %d%%" % int(WARN_RATIO * 100) if over80(s) else "OK"
        print("  %s  %d/%d 字符 (%.1f%%) · %d/%d 行 (%.1f%%)  %s"
              % (name, s["chars"], MAX_CHARS, s["pc"] * 100,
                 s["lines"], MAX_LINES, s["pl"] * 100, flag))
        print("       %s" % s["path"])
    print()
    print("=== 待整合候选（%d 条，只出提案，一条都不自动删）===" % len(cands))
    for c in cands:
        print("  #%-2d [%s:%d] %-12s %s" %
              (c["id"], c["scope"], c["lineno"], c["reason"], c["text"]))
        print("       建议：%s" % KIND_ACTION[c["kind"]])
    if cands:
        print()
        print("  要点头哪几条：python memory_check.py apply --ids 1,3 --confirm")
        print("  用户级条目只列出供查看，apply 不会改动它。")
    return 0


def apply_changes(workspace: str, ids, confirm: bool, scope: str, replaces) -> int:
    if scope == "user":
        print("拒绝：用户级 MEMORY.md 全空间共用，本脚本只读体检，不做任何改动。")
        print("     确需修改，请单独确认后手工执行，并自行量字符预算。")
        return 2
    ws = os.path.abspath(workspace)
    target = space_memory(ws)
    if not os.path.isfile(target):
        print("拒绝：找不到 %s" % target)
        return 2

    _, cands = candidates(ws)
    picked = [c for c in cands if c["id"] in ids and c["scope"] == "workspace"]
    missing = [i for i in ids if i not in [c["id"] for c in picked]]
    if missing:
        print("拒绝：这些编号不存在或属于用户级（只读）：%s" % missing)
        return 2
    if not picked:
        print("没有可处理的候选项。")
        return 0

    rep = {}
    for r in replaces:
        k, _, v = r.partition("=")
        try:
            rep[int(k.strip())] = v.strip()
        except ValueError:
            print("拒绝：--replace 格式应为 ID=新文本")
            return 2

    before = read(target)
    lines = before.splitlines()
    by_line = {c["lineno"]: c for c in picked}
    new_lines = []
    for i, ln in enumerate(lines, 1):
        if i in by_line:
            c = by_line[i]
            if c["id"] in rep:
                new_lines.append("- " + rep[c["id"]])
                c["done"] = "替换为：" + rep[c["id"]][:60]
            else:
                c["done"] = "删除"
            continue
        new_lines.append(ln)
    after = "\n".join(new_lines) + "\n"

    print("=== 记忆整合 %s ===" % ("执行" if confirm else "干跑（未写任何文件）"))
    for c in picked:
        print("  #%d [%s:%d] %s → %s" % (c["id"], c["scope"], c["lineno"],
                                          c["reason"], c["done"]))
    print("  字符：%d → %d｜行：%d → %d" %
          (len(before), len(after), len(lines), len(new_lines)))
    if not confirm:
        print("  确认无误后加 --confirm 才会写入。")
        return 0

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    bakdir = os.path.join(ws, BACKUP_REL)
    os.makedirs(bakdir, exist_ok=True)
    bak = os.path.join(bakdir, "MEMORY.%s.md" % stamp)
    shutil.copy2(target, bak)
    if sha256(bak) != sha256(target):
        print("拒绝：备份校验失败，未改动原文件。")
        return 2

    tmp = target + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(after)
    os.replace(tmp, target)

    report = os.path.join(ws, REPORT_REL)
    os.makedirs(os.path.dirname(report), exist_ok=True)
    exists = os.path.isfile(report)
    with io.open(report, "a", encoding="utf-8", newline="\n") as f:
        if not exists:
            f.write("# 记忆整合变更报告\n\n")
            f.write("| 时间 | 编号 | 行 | 理由 | 处置 | 备份 sha256 | 字符前后 |\n")
            f.write("|---|---|---|---|---|---|---|\n")
        for c in picked:
            f.write("| %s | #%d | %d | %s | %s | %s | %d→%d |\n" %
                    (stamp, c["id"], c["lineno"], c["reason"], c["done"],
                     sha256(bak)[:12], len(before), len(after)))
    print("  备份：%s" % bak)
    print("  报告：%s" % report)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="记忆预算体检与整合提案")
    ap.add_argument("cmd", choices=("check", "apply", "status"))
    ap.add_argument("--workspace", default=os.getcwd())
    ap.add_argument("--ids", default="")
    ap.add_argument("--confirm", action="store_true")
    ap.add_argument("--scope", choices=("workspace", "user"), default="workspace")
    ap.add_argument("--replace", action="append", default=[])
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    if a.cmd == "status":
        warn, text = budget_status(a.workspace)
        print(text if warn else "OK")
        return 0
    if a.cmd == "check":
        if a.out:
            import contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                print_check(a.workspace)
            os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
            with io.open(a.out, "w", encoding="utf-8", newline="\n") as f:
                f.write(buf.getvalue())
            print("清单已写入：%s" % a.out)
            return 0
        return print_check(a.workspace)
    try:
        ids = [int(x.strip()) for x in a.ids.split(",") if x.strip()]
    except ValueError:
        print("拒绝：--ids 应为逗号分隔的数字，如 1,3")
        return 2
    if not ids:
        print("拒绝：apply 必须逐条给 --ids（先跑 check 看编号）。")
        return 2
    return apply_changes(a.workspace, ids, a.confirm, a.scope, a.replace)


if __name__ == "__main__":
    sys.exit(main())
