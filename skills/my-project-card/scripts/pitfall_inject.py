#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SessionStart hook：注入跨空间高危坑提醒 ＋ 当前活跃交接摘要。

设计约束：
- 只依赖标准库；任何异常静默退出（exit 0），绝不阻塞会话启动
- 坑索引前 N 条（约 700 字符）＋ 交接摘要（≤220 字符），总量可控
- 数据源：references/pitfalls-INDEX.md；条目数由 <!-- inject: N --> 控制
- 交接摘要来自 ~/.workbuddy/handoff-active.json 指向的 HANDOVER.md（7 天过期）
- 输出统一走 stdout.buffer 显式 UTF-8（Windows 管道默认 cp936 会乱码，2026-11-08 实测）
- 每次运行写一行日志到 ~/.workbuddy/pitfalls/inject.log
"""
import io
import os
import re
import sys
import datetime

try:
    HOME = os.path.expanduser("~")
    IDX = os.path.join(HOME, ".workbuddy", "skills", "my-project-card", "references", "pitfalls-INDEX.md")
    LOG = os.path.join(HOME, ".workbuddy", "pitfalls", "inject.log")

    parts = []
    n_pit = 0
    n_hand = 0

    # ---- 1. 坑提醒 ----
    if os.path.isfile(IDX):
        text = io.open(IDX, encoding="utf-8").read()
        m = re.search(r"<!--\s*inject:\s*(\d+)\s*-->", text)
        limit = int(m.group(1)) if m else 8
        blocks = re.findall(r"###\s*\[([^\]]+)\]\s*(\S[^\n]*)\n((?:[-*][^\n]*\n?)+)", text)
        lines = []
        for cat, name, body in blocks[:limit]:
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
            act = re.sub(r"\s+", " ", act)[:64]
            lines.append("[%s] %s——%s" % (cat, name.strip(), act))
        if lines:
            n_pit = len(lines)
            parts.append(
                "<pitfall-reminder>\n开工先查坑（跨空间高危，出处 卡片技能 references/pitfalls-INDEX.md，涉及对应场景必须先遵守）：\n"
                + "\n".join("%d. %s" % (i + 1, ln) for i, ln in enumerate(lines))
                + "\n</pitfall-reminder>")

    # ---- 2. 交接摘要（复用 handoff.py，import 失败不影响坑提醒）----
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import handoff
        p = handoff.active_pointer()
        if p:
            sec = handoff.parse_sections(io.open(p, encoding="utf-8").read())
            goal = " ".join(sec.get("目标", "").split())[:52]
            nxt = " ".join(sec.get("下一步", "").split())[:72]
            pending = sec.get("未决问题", "").strip()
            n_pending = 0 if pending in ("", "无") else len(
                [x for x in pending.splitlines() if x.strip().startswith(("-", "*", "1", "2", "3"))]) or 1
            s = ("<handoff>\n上次交接：%s\n下一步：%s\n未决：%d 项｜全文 %s\n</handoff>"
                 % (goal, nxt, n_pending, p.replace("/", "\\")))
            if len(s) > handoff.SUMMARY_LIMIT:
                s = s[:handoff.SUMMARY_LIMIT - 12] + "\n</handoff>"
            parts.append(s)
            n_hand = 1
    except Exception:
        pass  # 静默：交接是增强项，失败不阻塞

    if parts:
        out = "\n".join(parts) + "\n"
        buf = getattr(sys.stdout, "buffer", None)
        if buf is not None:
            buf.write(out.encode("utf-8"))
            buf.flush()
        else:
            sys.stdout.write(out)

    try:
        if os.path.isfile(LOG) and os.path.getsize(LOG) > 20000:
            os.remove(LOG)
        with io.open(LOG, "a", encoding="utf-8") as f:
            f.write("%s injected=%d handoff=%d\n" % (
                datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), n_pit, n_hand))
    except Exception:
        pass
except Exception:
    pass  # 静默失败：hook 绝不能阻塞会话
sys.exit(0)
