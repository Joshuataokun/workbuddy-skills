#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HANDOVER · 上下文压缩前后的会话态承接（my-project-card 收编，原 workspace-converge v1.8.0）

设计要点：
- 平台自动压缩后仍在同一会话，但中间推理 / 已读文件内容 / 多步状态 / 口头偏好会丢。
  解法不是「一句话一个会话」，而是压缩前把会话态落到文件，压缩后文件仍在。
- HANDOVER 只写「卡片里没有的会话态」：目标、未决问题、下一步一句话；
  结论 / 坑 / 文件清单只留指针，不复制内容（收尾归属表：一事实只写一处）。
- 内容由助手（模型）写好传给脚本；脚本只负责字段校验、原子写、更新活跃指针。
  脚本不总结会话，不做不可逆删除。
- 输出统一走 stdout.buffer 显式 UTF-8（Windows 管道默认 cp936 会乱码）。

只依赖标准库。
"""
import argparse
import datetime as dt
import io
import json
import os
import sys

SECTIONS = ("目标", "已定口径与结论", "改过的文件", "踩过的坑", "未决问题", "下一步")
MAX_CHARS = 1500          # HANDOVER 全文上限（长了没人读，也不该复制长期状态）
POINTER_TTL_DAYS = 7      # 活跃指针超过 7 天不再注入
SUMMARY_LIMIT = 220       # 每会话注入上限，控制上下文税

HOME = os.path.expanduser("~")
POINTER = os.path.join(HOME, ".workbuddy", "handoff-active.json")
LOG = os.path.join(HOME, ".workbuddy", "handoff.log")


def emit(text):
    buf = getattr(sys.stdout, "buffer", None)
    if buf is not None:
        buf.write(text.encode("utf-8"))
        buf.flush()
    else:
        sys.stdout.write(text)


def handoff_path(space):
    return os.path.join(os.path.abspath(space), ".workbuddy", "HANDOVER.md")


def parse_sections(text):
    out = {}
    cur = None
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith("#"):
            title = s.lstrip("#").strip()
            if title in SECTIONS:
                cur = title
                out[cur] = []
                continue
        if cur:
            out[cur].append(ln.rstrip())
    return {k: "\n".join(v).strip() for k, v in out.items()}


def validate(text):
    if len(text) > MAX_CHARS:
        return "全文 %d 字符，超过 %d（结论/坑/文件清单请只留指针，不要复制）" % (len(text), MAX_CHARS)
    sec = parse_sections(text)
    missing = [s for s in SECTIONS if s not in sec]
    if missing:
        return "缺少小节: " + "、".join(missing)
    empty = [s for s in ("目标", "未决问题", "下一步") if not sec[s]]
    if empty:
        return "这些小节不能空（没有就写「无」）: " + "、".join(empty)
    return None


def atomic_write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def write_pointer(path, space):
    tmp = POINTER + ".tmp"
    data = {
        "path": path,
        "space": os.path.abspath(space),
        "updated": dt.datetime.now().isoformat(timespec="seconds"),
        "version": 1,
    }
    os.makedirs(os.path.dirname(POINTER), exist_ok=True)
    with io.open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False, indent=2))
    os.replace(tmp, POINTER)
    return data


def append_log(msg):
    try:
        if os.path.isfile(LOG) and os.path.getsize(LOG) > 20000:
            os.remove(LOG)
        with io.open(LOG, "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg))
    except Exception:
        pass


def active_pointer():
    """返回活跃 HANDOVER 路径；不存在 / 损坏 / 过期 / 文件消失 → None。"""
    if not os.path.isfile(POINTER):
        return None
    try:
        d = json.load(io.open(POINTER, encoding="utf-8"))
        t = dt.datetime.fromisoformat(d["updated"])
        if (dt.datetime.now() - t).days > POINTER_TTL_DAYS:
            return None
        p = d["path"]
        if not os.path.isfile(p):
            return None
        return p
    except Exception:
        return None


def cmd_save(a):
    space = os.path.abspath(a.space)
    src = a.content
    text = io.open(src, encoding="utf-8").read() if os.path.isfile(src) else src
    err = validate(text)
    if err:
        emit("交接未写入：%s\n" % err)
        return 2
    p = handoff_path(space)
    atomic_write(p, text.strip() + "\n")
    write_pointer(p, space)
    append_log("save %s (%d chars)" % (p, len(text)))
    emit("已交接: %s（%d 字符）\n活跃指针已更新，现在可以压缩了。\n" % (p, len(text)))
    return 0


def cmd_show(a):
    p = active_pointer()
    if not p:
        emit("没有有效的活跃交接（指针不存在/过期/文件已移走）\n")
        return 0
    emit(io.open(p, encoding="utf-8").read())
    return 0


def cmd_clear(a):
    """任务完成后归档交接（不删），并撤销活跃指针。"""
    space = os.path.abspath(a.space)
    p = handoff_path(space)
    if os.path.isfile(p):
        arch = os.path.join(space, ".workbuddy", "archive",
                            "handoff-%s.md" % dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
        os.makedirs(os.path.dirname(arch), exist_ok=True)
        os.replace(p, arch)
        emit("已归档交接: %s（未删除）\n" % arch)
    try:
        if os.path.isfile(POINTER):
            os.remove(POINTER)
        emit("活跃指针已撤销，下个会话不再注入\n")
    except Exception as e:
        emit("指针撤销失败: %s\n" % e)
    append_log("clear %s" % space)
    return 0


def cmd_summary(a):
    """给 SessionStart 注入用：只出极简摘要，绝不超过 SUMMARY_LIMIT。"""
    p = active_pointer()
    if not p:
        return 0
    try:
        sec = parse_sections(io.open(p, encoding="utf-8").read())
    except Exception:
        return 0
    goal = " ".join(sec.get("目标", "").split())[:52]
    nxt = " ".join(sec.get("下一步", "").split())[:72]
    pending = sec.get("未决问题", "").strip()
    n_pending = 0 if pending in ("", "无") else len([x for x in pending.splitlines() if x.strip().startswith(("-", "*", "1", "2", "3"))]) or 1
    short = p.replace("/", "\\")
    out = ("<handoff>\n上次交接：%s\n下一步：%s\n未决：%d 项｜全文 %s\n</handoff>"
           % (goal, nxt, n_pending, short))
    if len(out) > SUMMARY_LIMIT:
        out = out[:SUMMARY_LIMIT - 12] + "\n</handoff>"
    emit(out)
    return 0


def main():
    ap = argparse.ArgumentParser(description="上下文压缩前后的会话态承接")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("save", help="写入 HANDOVER 并更新活跃指针")
    p.add_argument("--space", required=True, help="当前空间根目录")
    p.add_argument("--content", required=True, help="内容文本，或写好的 .md 文件路径")
    p.set_defaults(func=cmd_save)
    p = sub.add_parser("show", help="读当前活跃交接全文")
    p.set_defaults(func=cmd_show)
    p = sub.add_parser("clear", help="任务完成：归档交接并撤销指针（不删除）")
    p.add_argument("--space", required=True)
    p.set_defaults(func=cmd_clear)
    p = sub.add_parser("summary", help="SessionStart 注入用的极简摘要（静默）")
    p.set_defaults(func=cmd_summary)
    a = ap.parse_args()
    if not getattr(a, "func", None):
        ap.print_help()
        return 0
    return a.func(a)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as ex:
        emit("handoff.py 出错: %s: %s\n" % (type(ex).__name__, ex))
        sys.exit(2)
