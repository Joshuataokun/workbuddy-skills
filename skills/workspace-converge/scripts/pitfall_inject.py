#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SessionStart hook：注入跨空间高危坑提醒。

设计约束：
- 只依赖标准库；任何异常静默退出（exit 0），绝不阻塞会话启动
- 输出 ≤ 400 字符（每会话的上下文税要可控）
- 数据源 pitfalls/INDEX.md；条目数由 <!-- inject: N --> 控制
- 每次运行写一行日志到 pitfalls/inject.log（供新会话验证 hook 是否生效）
"""
import io
import os
import re
import sys
import datetime

try:
    HOME = os.path.expanduser("~")
    IDX = os.path.join(HOME, ".workbuddy", "skills", "workspace-converge", "references", "pitfalls-INDEX.md")
    LOG = os.path.join(HOME, ".workbuddy", "pitfalls", "inject.log")

    if not os.path.isfile(IDX):
        sys.exit(0)  # 无索引＝无提醒，静默

    text = io.open(IDX, encoding="utf-8").read()

    m = re.search(r"<!--\s*inject:\s*(\d+)\s*-->", text)
    limit = int(m.group(1)) if m else 8

    blocks = re.findall(r"###\s*\[([^\]]+)\]\s*(\S[^\n]*)\n((?:[-*][^\n]*\n?)+)", text)
    if not blocks:
        sys.exit(0)

    lines = []
    for cat, name, body in blocks[:limit]:
        # 取"做法"行（- 做法：...），没有就用第一行
        act = ""
        for ln in body.splitlines():
            if ln.strip().startswith(("- 做法", "* 做法")):
                act = ln.split("：", 1)[-1].split(":", 1)[-1].strip()
                break
        if not act:
            for ln in body.splitlines():
                if ln.strip().startswith("-"):
                    act = ln.strip().lstrip("-* ").strip()
                    break
        act = re.sub(r"\s+", " ", act)[:64]  # 截断，控制注入体量
        lines.append("[%s] %s——%s" % (cat, name.strip(), act))

    if not lines:
        sys.exit(0)

    out = "<pitfall-reminder>\n开工先查坑（跨空间高危，出处 收敛技能 references/pitfalls-INDEX.md，涉及对应场景必须先遵守）：\n" + "\n".join(
        "%d. %s" % (i + 1, ln) for i, ln in enumerate(lines)) + "\n</pitfall-reminder>"

    sys.stdout.write(out)

    # 运行日志（验证 hook 生效用；>200 行自动清）
    try:
        if os.path.isfile(LOG) and os.path.getsize(LOG) > 20000:
            os.remove(LOG)
        with io.open(LOG, "a", encoding="utf-8") as f:
            f.write("%s injected=%d\n" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), len(lines)))
    except Exception:
        pass
except Exception:
    pass  # 静默失败：hook 绝不能阻塞会话
sys.exit(0)
