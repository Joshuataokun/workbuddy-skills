#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""my-project-card · 清理脚本共用的防误删护栏

2026-11-11 从 workspace-converge/scripts/ttl.py 抽出，只保留 wrap_cleanup.py
实际用到的五个符号，TTL 到期清理那套逻辑整个不搬（用户判定压缩上下文无意义）。

保留清单（行为与原 ttl.py 完全一致，勿擅自改）：
- PIN_MARKERS / GENERIC_NAMES / MAX_PURGE_BYTES
- sha256() / collect_refs() / referenced()

只依赖标准库。本模块被 wrap_cleanup.py 以 `import guard_common as ttl` 引用，
别名保持 `ttl` 是为了让调用侧零改动、22 项验收语义不变。
"""
from __future__ import annotations

import glob
import hashlib
import io
import os

# 只要路径里出现这些片段，整个目录视为 pin（原件/资产/回滚点）
PIN_MARKERS = (
    "memory-snapshot", "memory-20", "backups", ".workbuddy\\archive",
    ".workbuddy/archive", "workbuddy-skills-repo", "baseline",
    "out\\assets", "out/assets", "/out/", "h5-patch",
    "node_modules", "dist", "release",
)
# 极常见的通用文件名：不凭「别处提到过同名」就永久保留
GENERIC_NAMES = {
    "build.py", "extract.py", "match.py", "index.html", "main.py",
    "test.py", "config.json", "data.json", "tmp.json", "run.py",
    "setup.py", "utils.py", "readme.txt", "output.log",
}
MAX_PURGE_BYTES = 1000000  # 超过 1MB 一律当原件保守处理


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def collect_refs(extra_files=()):
    """引用源：所有空间 MEMORY.md + 日志 + 指定的自动化 prompt 导出文本。"""
    text = []
    for p in glob.glob(r"E:\WorkBuddy\*\.workbuddy\memory\*.md"):
        try:
            text.append(io.open(p, encoding="utf-8", errors="replace").read())
        except Exception:
            pass
    for p in extra_files:
        if p and os.path.isfile(p):
            try:
                text.append(io.open(p, encoding="utf-8", errors="replace").read())
            except Exception:
                pass
    return "\n".join(text)


def referenced(rel, refs):
    """强引用（完整相对路径或末两段）才拦；通用文件名不凭同名拦。"""
    parts = rel.replace("\\", "/").split("/")
    if rel.replace("\\", "/") in refs:
        return rel
    if len(parts) >= 2:
        tail2 = "/".join(parts[-2:])
        if len(tail2) >= 10 and tail2 in refs:
            return tail2
    base = parts[-1]
    if base.lower() in GENERIC_NAMES:
        return None
    if len(base) >= 6 and base in refs:
        return base
    return None
