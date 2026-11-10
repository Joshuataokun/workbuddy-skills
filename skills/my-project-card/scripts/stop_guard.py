#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""my-project-card · Stop 守卫（漏记拦截）

挂在用户级 `Stop` hook 上。每次助手答完触发，只在下面四个条件**全部**成立时
拦一次收工，把补卡指令塞回对话：

  1. 当前 cwd 能对应到一张已建的项目卡；
  2. 本轮（最后一条用户消息之后）确实动了文件；
  3. 本轮这张卡的事件流里没有 add / revise / claim；
  4. 本轮还没被拦过（stop_hook_active 为 false）。

其余一律静默放行。任何异常、缺字段、拿不准的情况都放行——守卫宁可漏拦，
绝不把会话卡死。想整体停用：在卡片库目录放一个 `.stop-guard-off` 文件。

输出协议（WorkBuddy/CodeBuddy Hooks Reference）：
  拦截 → stdout 打印 {"continue": false, "reason": "..."}，退出码 0
  放行 → stdout 不输出任何东西，退出码 0
调试信息一律写日志文件，绝不打印到 stdout（会破坏 JSON 解析）。
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
from collections import deque
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
CARD_PY = os.path.join(SKILL_DIR, "card.py")

_spec = importlib.util.spec_from_file_location("card_engine", CARD_PY)
card = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(card)

STORE = os.path.abspath(os.environ.get("CARD_STORE") or card.DEFAULT_STORE)
DEBUG = os.environ.get("CARD_STOP_GUARD_DEBUG") == "1"
OFF_FILE = os.path.join(STORE, ".stop-guard-off")

# 明确写文件的工具：看到就算本轮有改动
WRITE_TOOLS = {
    "Write", "Edit", "MultiEdit", "NotebookEdit", "apply_patch",
    "write_file", "create_file", "replace_in_file", "delete_file",
    "str_replace_editor", "file_write",
}
# 命令型工具：只认强写标志，宁可漏判也不误判
CMD_TOOLS = {"Bash", "PowerShell", "execute_command", "Shell"}
WRITE_CMD = re.compile(
    r"(?:\b(?:rm|mv|cp|mkdir|rmdir|touch|chmod|chown|tee|install|unlink)\b"
    r"|\bgit\s+(?:add|commit|push|checkout|reset|merge|rebase|restore|stash)\b"
    r"|\b(?:npm|pnpm|yarn)\s+(?:install|add)\b"
    r"|\bpip(?:3)?\s+install\b"
    r"|\bsed\s+-i\b"
    r"|(?:Set|Add)-Content\b|Out-File\b|(?:New|Remove|Move|Copy)-Item\b"
    r"|\bpython[^\n]*-c[^\n]*(?:open\(|\.write|json\.dump|os\.replace|shutil\.)"
    r"|\b(?:echo|printf|cat)\b[^\n]*\s>>?\s*\S)",
    re.I)


def allow(why: str = "") -> None:
    """放行：stdout 必须干净。"""
    if DEBUG and why:
        card.guard_write(STORE, {"k": "skip", "why": why})
    sys.exit(0)


def log(rec: dict) -> None:
    if DEBUG or rec.get("k") in ("block", "miss"):
        card.guard_write(STORE, rec)


def read_tail(path: str, maxlines: int = 800):
    """只读 transcript 尾部，长会话也不会拖慢 hook。"""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = deque(f, maxlen=maxlines)
    out = []
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def ms_to_iso(ms) -> str:
    try:
        return datetime.fromtimestamp(float(ms) / 1000).strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:
        return ""


def find_card(cwd: str):
    """用卡片主卡的 workspaces: 反查当前工作区属于哪张卡，支持子目录。"""
    if not cwd or not os.path.isdir(STORE):
        return None
    target = os.path.normcase(os.path.abspath(cwd))
    best = None
    try:
        entries = sorted(os.listdir(STORE))
    except Exception:
        return None
    for d in entries:
        p = card.main_path(STORE, d)
        if not os.path.isfile(p):
            continue
        try:
            ws = card.meta_workspaces(p)
        except Exception:
            continue
        for w in ws:
            nw = os.path.normcase(os.path.abspath(w))
            if target == nw or target.startswith(nw + os.sep):
                if best is None or len(nw) > len(best[1]):
                    best = (d, nw)
    return best[0] if best else None


def turn_info(objs):
    """返回 (本轮起始索引, 本轮起始 ISO)。找不到用户消息就返回 (None, '')。"""
    idx = None
    for i in range(len(objs) - 1, -1, -1):
        o = objs[i]
        if o.get("type") == "message" and o.get("role") == "user":
            idx = i
            break
    if idx is None:
        return None, ""
    iso = ms_to_iso(objs[idx].get("timestamp"))
    try:
        # 秒级精度留一秒容差，避免边界处把刚写的卡判成上一轮
        iso = (datetime.strptime(iso, "%Y-%m-%dT%H:%M:%S") - timedelta(seconds=1)) \
            .strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:
        return idx, ""
    return idx, iso


def looks_like_write(cmd: str) -> bool:
    return bool(WRITE_CMD.search(cmd or ""))


def changed_this_turn(objs, start_idx, turn_iso) -> bool:
    for o in objs[start_idx + 1:]:
        typ = o.get("type")
        if typ == "function_call":
            name = o.get("name") or ""
            if name in WRITE_TOOLS:
                return True
            if name in CMD_TOOLS:
                args = o.get("arguments")
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {"command": args}
                cmd = str(args.get("command") or args.get("cmd") or "") \
                    if isinstance(args, dict) else ""
                if looks_like_write(cmd):
                    return True
        elif typ == "file-history-snapshot" and o.get("isSnapshotUpdate"):
            ts = ms_to_iso(o.get("timestamp"))
            if turn_iso and ts >= turn_iso:
                return True
    return False


def wrote_card_this_turn(slug: str, turn_iso: str) -> bool:
    if not turn_iso:
        return False
    try:
        rows = card.journal_all(STORE, slug)
    except Exception:
        return False
    return any(r.get("t", "") >= turn_iso and r.get("a") in ("add", "revise", "claim")
               for r in rows)


def reason_text(slug: str, cwd: str) -> str:
    return (
        "本轮在「%s」这张项目卡对应的空间里改了文件，但卡片事件流没有本轮的写入记录。"
        "收工前请补一条：把 <本轮结论> 换成实际做完的事或新定的口径，用命令 "
        "python \"%s\" add --slug %s --section 进度 --text \"<本轮结论>\" "
        "--workspace \"%s\" 写进卡片（分册改动加 --book 和 --section 已完成）。"
        "只写事实，不写套话和推测。若本轮确实只是查资料、试跑或纯问答、没产生需要留存的结论，"
        "直接说明一句理由即可收工，不必硬凑一条。"
    ) % (slug, CARD_PY, slug, cwd)


def block(slug: str, cwd: str, sid: str, turn_iso: str) -> None:
    log({"k": "block", "sid": sid, "slug": slug, "turn": turn_iso,
         "cwd": cwd, "why": "本轮有改动但没写卡"})
    print(json.dumps({
        "continue": False,
        "reason": reason_text(slug, cwd),
    }, ensure_ascii=False))
    sys.exit(0)


def after_continue(sid: str) -> None:
    """被拦后的第二次 Stop：放行，但记下「提醒后仍未补卡」，供 audit 查。"""
    try:
        rows = [x for x in card.guard_read(STORE)
                if x.get("k") == "block" and x.get("sid") == sid]
        if not rows:
            return
        last = rows[-1]
        # 只认十分钟内的拦截，避免旧记录串到新任务
        try:
            age = (datetime.now() - datetime.strptime(
                last.get("t", ""), "%Y-%m-%dT%H:%M:%S")).total_seconds()
        except Exception:
            return
        if age > 600:
            return
        slug, turn = last.get("slug", ""), last.get("turn", "")
        if slug and not wrote_card_this_turn(slug, turn):
            log({"k": "miss", "sid": sid, "slug": slug, "turn": turn,
                 "why": "被提醒后仍未写卡"})
    except Exception:
        pass


def main() -> None:
    try:
        raw = sys.stdin.read() or "{}"
        inp = json.loads(raw)
    except Exception:
        return allow("输入不是 JSON")

    sid = str(inp.get("session_id") or "")
    cwd = str(inp.get("cwd") or os.getcwd())
    tp = inp.get("transcript_path") or ""

    if os.path.isfile(OFF_FILE):
        return allow("总开关关闭")
    if inp.get("stop_hook_active"):
        after_continue(sid)
        return allow("本轮已续跑过，放行")

    slug = find_card(cwd)
    if not slug:
        return allow("该工作区没有卡片")
    if not tp or not os.path.isfile(tp):
        return allow("没有 transcript，放行")

    objs = read_tail(tp)
    start_idx, turn_iso = turn_info(objs)
    if start_idx is None or not turn_iso:
        return allow("切不出本轮边界，放行")
    if not changed_this_turn(objs, start_idx, turn_iso):
        return allow("本轮没动文件，放行")
    if wrote_card_this_turn(slug, turn_iso):
        return allow("本轮已写卡，放行")

    block(slug, cwd, sid, turn_iso)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        # fail-open：守卫自身出错绝不能拖住收工
        allow("守卫异常，放行")
