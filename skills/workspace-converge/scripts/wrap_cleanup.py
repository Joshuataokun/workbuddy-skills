#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""workspace-converge · Stop 时刻清理「本轮新建的中间产物」（A 档第 4 条）

用户 2026-11-10 拍板：不合并到卡片技能；收尾走同一个 Stop 时刻；
清理沿用 TTL 模式——首次强制 dry-run 只出清单，第二次起按白名单自动删、留台账。

护栏（比 ttl.py 更窄，只认明确的临时物）：
- 只读扫描当前空间，个人目录 / 盘符根 / 非空间目录一律不扫
- 只删白名单：__pycache__ 等缓存目录内容、*.pyc/*.pyo/*.tmp、
  以及带 tmp_/test_/parse_/diag_ 前缀的 json/html/xlsx/log/out
- 一律 pin：交付物扩展名、>1MB、被引用、路径越界、pin 目录、拿不准的
- 单轮最多 10 个；删前备份到隔离区并校验 sha256；写 ledger；幂等
- 首次运行强制 dry-run（写 armed: true），之后才真删
- hook 协议：stdout 必须为空、exit 0；所有信息写日志文件；异常一律放行

复用 ttl.py 的 sha256 / collect_refs / referenced / PIN_MARKERS / MAX_PURGE_BYTES，
不重复造护栏（见 references/changelog.md v1.6.0「不重复造」）。
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import io
import json
import os
import re
import shutil
import sys
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("ttl_engine", os.path.join(HERE, "ttl.py"))
ttl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ttl)

# 验收时用 WRAP_CLEANUP_HOME 指向临时目录，绝不碰真实卡库/台账
HOME = os.path.abspath(os.environ.get("WRAP_CLEANUP_HOME") or os.path.expanduser("~"))
OFF_FILE = os.path.join(HOME, ".workbuddy", ".wrap-cleanup-off")
STATE_ROOT = os.path.join(HOME, ".workbuddy", "archive", "wrap-cleanup")
LOG_PATH = os.path.join(STATE_ROOT, "wrap.log")
LEDGER_REL = os.path.join(".workbuddy", "archive", "wrap-ledger.md")
PLAN_REL = os.path.join(".workbuddy", "archive", "wrap-首次清单.md")
ARMED_LINE = "armed: true"

MAX_PER_TURN = 10
MAX_WALK_FILES = 6000
MAX_DEPTH = 8

JUNK_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache"}
JUNK_EXTS = {".pyc", ".pyo", ".tmp"}
JUNK_PREFIX = ("tmp_", "test_", "parse_", "diag_")
JUNK_PREFIX_EXTS = {".json", ".html", ".xlsx", ".log", ".out"}
# 这些扩展名一律按交付物/原件处理，绝不自动删
DELIVERABLE_EXTS = {
    ".md", ".markdown", ".docx", ".doc", ".pdf", ".png", ".jpg", ".jpeg",
    ".gif", ".zip", ".pptx", ".ppt", ".csv", ".tsv", ".txt", ".ps1",
    ".bat", ".sh", ".py", ".js", ".ts", ".json5", ".yaml", ".yml", ".toml",
}
SKIP_DIRS = {
    ".git", ".workbuddy", "node_modules", ".venv", "venv", "dist", "release",
    "backups", "backup", "archive", "_archive", "_cleared-", "publish-",
    "workbuddy-skills-repo", "out", "assets", "baseline",
}


def log(rec: dict) -> None:
    """只写文件，绝不碰 stdout（会破坏 hook 的 JSON 判定）。"""
    try:
        os.makedirs(STATE_ROOT, exist_ok=True)
        rec = dict(rec)
        rec.setdefault("t", dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))
        with io.open(LOG_PATH, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        lines = io.open(LOG_PATH, encoding="utf-8", errors="replace").read().splitlines()
        if len(lines) > 2000:
            tmp = LOG_PATH + ".tmp"
            with io.open(tmp, "w", encoding="utf-8", newline="\n") as f:
                f.write("\n".join(lines[-400:]) + "\n")
            os.replace(tmp, LOG_PATH)
    except Exception:
        pass


def no_go(cwd: str) -> bool:
    """个人目录 / 系统目录 / 盘符根 / 非空间目录，一律不扫不删。"""
    low = os.path.normcase(os.path.abspath(cwd))
    home = os.path.normcase(os.path.abspath(HOME))
    if low == home or re.match(r"^[a-z]:\\?$", low):
        return True
    for name in ("desktop", "downloads", "documents", "onedrive",
                 "appdata", "library", ".config", ".ssh", ".aws"):
        p = os.path.normcase(os.path.abspath(os.path.join(HOME, name)))
        if low == p or low.startswith(p + os.sep):
            return True
    drive = os.path.splitdrive(low)[0] + os.sep
    for name in ("windows", "program files", "program files (x86)", "system32"):
        p = os.path.normcase(os.path.join(drive, name))
        if low == p or low.startswith(p + os.sep):
            return True
    # 必须是具体工作空间（有 .workbuddy 目录），避免扫到所有空间的父目录
    if not os.path.isdir(os.path.join(cwd, ".workbuddy")):
        return True
    return False


def turn_start_seconds(transcript_path: str):
    """从 transcript 尾部找最后一条用户消息，返回本轮起始 epoch 秒。"""
    with io.open(transcript_path, encoding="utf-8", errors="replace") as f:
        tail = deque(f, maxlen=800)
    rows = []
    for ln in tail:
        ln = ln.strip()
        if ln:
            try:
                rows.append(json.loads(ln))
            except Exception:
                pass
    for o in reversed(rows):
        if o.get("type") == "message" and o.get("role") == "user":
            try:
                return float(o["timestamp"]) / 1000.0 - 1.0  # 秒级容差
            except Exception:
                return None
    return None


def is_junk(rel: str):
    """白名单式判定：不明确命中就返回 False（拿不准就保留）。"""
    low = rel.replace("\\", "/").lower()
    parts = low.split("/")
    if any(p in JUNK_DIRS for p in parts[:-1]):
        return True, "缓存目录内"
    base = parts[-1]
    ext = os.path.splitext(base)[1].lower()
    if ext in JUNK_EXTS:
        return True, "临时/缓存文件"
    if base.startswith(JUNK_PREFIX) and ext in JUNK_PREFIX_EXTS:
        return True, "带临时前缀的中间产物"
    return False, ""


def pinned(rel: str, size: int, refs: str):
    low = rel.replace("\\", "/").lower()
    for m in ttl.PIN_MARKERS:
        if m in low:
            return "原件/资产/回滚点:" + m
    ext = os.path.splitext(rel)[1].lower()
    if ext in DELIVERABLE_EXTS:
        return "交付物/源码扩展名"
    if size > ttl.MAX_PURGE_BYTES:
        return "大于 1MB，按原件保守处理"
    hit = ttl.referenced(rel, refs)
    if hit:
        return "被引用:" + hit
    return ""


def collect(cwd: str, since: float, refs: str):
    root = os.path.abspath(cwd)
    found, seen = [], 0
    for dirpath, dirnames, filenames in os.walk(root):
        depth = dirpath[len(root):].count(os.sep)
        if depth >= MAX_DEPTH:
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            seen += 1
            if seen > MAX_WALK_FILES or len(found) >= MAX_PER_TURN * 3:
                return found
            full = os.path.join(dirpath, name)
            try:
                st = os.stat(full)
            except Exception:
                continue
            if st.st_mtime < since:
                continue
            rel = os.path.relpath(full, root)
            if not os.path.abspath(full).startswith(root + os.sep):
                continue
            ok, why = is_junk(rel)
            if not ok:
                continue
            why_pin = pinned(rel, st.st_size, refs)
            found.append({"abs": full, "rel": rel, "size": st.st_size,
                          "mtime": st.st_mtime, "why": why,
                          "pin": why_pin})
    return found


def ledger_path(cwd: str) -> str:
    return os.path.join(cwd, LEDGER_REL)


def is_armed(cwd: str) -> bool:
    p = ledger_path(cwd)
    if not os.path.isfile(p):
        return False
    try:
        return ARMED_LINE in io.open(p, encoding="utf-8").read()
    except Exception:
        return False


def write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, path)


def render_plan(cwd, cands, armed: bool) -> str:
    lines = ["# 收尾清理清单", "",
             "- 时间：%s" % dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
             "- 空间：%s" % cwd,
             "- 状态：%s" % ("本次为首次 dry-run，**零删除**；下一次 Stop 起按此白名单自动删"
                             if not armed else "按白名单自动删（已 armed）"),
             "- 备份目录：%s" % os.path.join(STATE_ROOT, "backup"),
             "- 停用：新建空文件 `%s`" % OFF_FILE,
             "", "| 文件 | 字节 | 理由 | 判定 |", "|---|---|---|---|"]
    for c in cands:
        lines.append("| %s | %d | %s | %s |" % (
            c["rel"], c["size"], c["why"], c["pin"] or "可删"))
    lines += ["", "只删上表中「可删」且单轮前 %d 项；其余一律保留。" % MAX_PER_TURN, ""]
    return "\n".join(lines)


def arm(cwd: str, plan_text: str) -> None:
    p = ledger_path(cwd)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    if not os.path.isfile(p):
        with io.open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write("# 收尾清理台账\n\n%s\n\n" % ARMED_LINE)
            f.write("| 时间 | 文件 | 字节 | sha256(前12) | 备份 | 理由 |\n")
            f.write("|---|---|---|---|---|---|\n")
    elif not is_armed(cwd):
        with io.open(p, "a", encoding="utf-8", newline="\n") as f:
            f.write("\n%s\n" % ARMED_LINE)
    write_text(os.path.join(cwd, PLAN_REL), plan_text)


def purge(cwd: str, cands) -> int:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    bakroot = os.path.join(STATE_ROOT, "backup", stamp)
    rows, removed = [], 0
    for c in cands:
        if not c["pin"] and removed >= MAX_PER_TURN:
            break
        if c["pin"]:
            continue
        p = c["abs"]
        if not os.path.isfile(p) or not os.path.abspath(p).startswith(
                os.path.abspath(cwd) + os.sep):
            continue
        try:
            st = os.stat(p)
            if st.st_size != c["size"] or abs(st.st_mtime - c["mtime"]) > 1:
                continue  # 扫描后被改动 → 本轮放弃
            sha = ttl.sha256(p)
            dst = os.path.join(bakroot, c["rel"])
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(p, dst)
            if ttl.sha256(dst) != sha:
                continue  # 备份校验失败 → 不删
            os.remove(p)
        except Exception:
            continue
        removed += 1
        rows.append("| %s | %s | %d | %s | %s | %s |\n" % (
            dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), c["rel"],
            c["size"], sha[:12], os.path.relpath(dst, STATE_ROOT), c["why"]))
    if rows:
        p = ledger_path(cwd)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with io.open(p, "a", encoding="utf-8", newline="\n") as f:
            f.writelines(rows)
    return removed


def main() -> None:
    try:
        inp = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return
    if os.path.isfile(OFF_FILE) or inp.get("stop_hook_active"):
        return
    cwd = os.path.abspath(str(inp.get("cwd") or os.getcwd()))
    tp = inp.get("transcript_path") or ""
    if no_go(cwd) or not tp or not os.path.isfile(tp):
        return
    try:
        since = turn_start_seconds(tp)
        if since is None:
            return
        refs = ttl.collect_refs()
        cands = collect(cwd, since, refs)
        armed = is_armed(cwd)
        plan = render_plan(cwd, cands, armed)
        if not cands:
            log({"k": "empty", "cwd": cwd, "cands": 0})
            return
        if not armed:
            arm(cwd, plan)
            log({"k": "dry-run", "cwd": cwd, "cands": len(cands),
                 "files": [c["rel"] for c in cands[:MAX_PER_TURN]],
                 "why": "首次启用强制 dry-run，零删除"})
            return
        n = purge(cwd, cands)
        log({"k": "purge", "cwd": cwd, "cands": len(cands), "removed": n,
             "files": [c["rel"] for c in cands[:MAX_PER_TURN]]})
        write_text(os.path.join(cwd, PLAN_REL), plan)
    except Exception as ex:
        log({"k": "error", "cwd": cwd, "why": "%s: %s" % (type(ex).__name__, ex)})


if __name__ == "__main__":
    # fail-open：守卫自身出错绝不能拖住收工，stdout 永远为空
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
