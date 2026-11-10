#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""我的项目卡片 · 引擎 2.0

定位：多会话共享的项目状态板。
  1. 谁在干什么  —— sessions.json + 心跳
  2. 都发生过什么 —— journal/ 追加式事件流
  3. 不丢数据    —— 文件锁 + 原子写 + 备份去重

命令：
  init    建卡（主卡 + 可选分册）
  add     追加一条（自动登记工作区、写事件流、查重）
  revise  改写一条（旧条目自动标失效，人不碰文件）
  claim   声明「我要动这个工作面」
  release 收工释放
  resume  开工简报（默认只读，四十行内）
  show    看全文
  search  检索
  check   体检
  list    列卡
  book    新建/列出分册
  mirror  只刷新工作区简报
  gc      备份收敛 + 事件流归档
  audit   查漏：读过卡却没写卡 / Stop 拦截记录
"""
from __future__ import annotations

import argparse
import contextlib
import difflib
import glob
import hashlib
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime, timedelta

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    import msvcrt
except ImportError:
    msvcrt = None
try:
    import fcntl
except ImportError:
    fcntl = None

HOME = os.path.expanduser("~")
DEFAULT_STORE = os.path.join(HOME, ".workbuddy", "cards")
MAIN_NAME = "context-card.md"
MIRROR_REL = os.path.join(".workbuddy", "PROJECT_CONTEXT.md")
PLACEHOLDER = "_（暂无记录）_"

MAIN_SECTIONS = [
    ("goal", "项目目标"),
    ("constraints", "口径与约束"),
    ("rejected", "已排除方案"),
    ("done", "已完成"),
    ("progress", "当前进度"),
    ("open", "待确认"),
    ("assets", "关键位置"),
]
BOOK_SECTIONS = [
    ("duty", "职责与范围"),
    ("constraints", "口径与约束"),
    ("done", "已完成"),
    ("todo", "待办"),
    ("pitfall", "踩过的坑"),
    ("assets", "关键位置"),
]

ALIASES = {
    "目标": "goal", "goal": "goal",
    "口径": "constraints", "约束": "constraints", "constraints": "constraints",
    "排除": "rejected", "已排除": "rejected", "rejected": "rejected",
    "完成": "done", "已完成": "done", "done": "done",
    "进度": "progress", "当前进度": "progress", "下一步": "progress", "progress": "progress",
    "待确认": "open", "open": "open",
    "位置": "assets", "文件": "assets", "关键位置": "assets", "assets": "assets",
    "职责": "duty", "范围": "duty", "duty": "duty",
    "待办": "todo", "todo": "todo",
    "坑": "pitfall", "踩坑": "pitfall", "踩过的坑": "pitfall", "pitfall": "pitfall",
}

SPEC_WORDS = ["应该", "可能是", "大概", "估计", "也许是", "我猜", "猜测",
              "或许是", "看上去像", "八成", "感觉是", "大概率"]
CRED_PAT = re.compile(
    r"(password|passwd|pwd|token|secret|api[_-]?key|access[_-]?key|private[_-]?key"
    r"|密码|口令|密钥|私钥|秘钥|令牌|连接串)\s*[:=＝:]\s*\S+", re.I)
ITEM_RE = re.compile(r"^-\s*【([^】]*)】\s*(?:#([0-9a-f]{4,8})\s+)?(.*)$")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
STALE_SESSION_MIN = 40


# ------------------------------------------------------------------ 基础
def now_dt() -> datetime:
    return datetime.now()


def today() -> str:
    return now_dt().strftime("%Y-%m-%d")


def now_iso() -> str:
    return now_dt().strftime("%Y-%m-%dT%H:%M:%S")


def human_ago(iso: str) -> str:
    try:
        d = now_dt() - datetime.strptime(iso, "%Y-%m-%dT%H:%M:%S")
    except Exception:
        return "时间不明"
    m = int(d.total_seconds() // 60)
    if m < 1:
        return "刚刚"
    if m < 60:
        return "%d 分钟前" % m
    if m < 1440:
        return "%d 小时前" % (m // 60)
    return "%d 天前" % (m // 1440)


def read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_atomic(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.tmp.%d" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


@contextlib.contextmanager
def card_lock(carddir: str, timeout: float = 10.0):
    """跨进程互斥。两个会话同时改同一张卡时排队，不互相覆盖。"""
    os.makedirs(carddir, exist_ok=True)
    lp = os.path.join(carddir, ".lock")
    f = open(lp, "a+b")
    if os.path.getsize(lp) == 0:
        f.write(b"L")
        f.flush()
    start = time.time()
    while True:
        try:
            if msvcrt:
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except OSError:
            if time.time() - start > timeout:
                f.close()
                fail("另一个会话正在写这张卡，等了 %.0f 秒仍被占用。稍后重试。" % timeout)
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            if msvcrt:
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        finally:
            f.close()


def fail(msg: str) -> None:
    print("✗ " + msg)
    sys.exit(1)


def slugify(name: str) -> str:
    s = re.sub(r"[\\/:*?\"<>|\s]+", "-", name.strip())
    s = re.sub(r"-+", "-", s).strip("-")
    return (s or "p" + now_dt().strftime("%Y%m%d%H%M%S"))[:60]


def alias_of(cwd: str) -> str:
    """把工作区路径变成人能读的短名。数字目录转成「空间-月日」。"""
    base = os.path.basename(str(cwd).rstrip("\\/"))
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})-(\d{2})-(\d{2})-(\d{2})$", base)
    if m:
        return "空间%s%s" % (m.group(2), m.group(3))
    return base[:12] or "未知"


def new_id(text: str) -> str:
    raw = (text + now_iso() + str(os.getpid())).encode("utf-8")
    return hashlib.md5(raw).hexdigest()[:4]


def worktag(cwd: str | None = None) -> str:
    """工作区身份：同一目录恒定，两个字以上可读。"""
    p = os.path.abspath(cwd or os.getcwd())
    return hashlib.md5(p.encode("utf-8")).hexdigest()[:4]


# ------------------------------------------------------------------ 结构
def sections_of(kind: str):
    return MAIN_SECTIONS if kind == "main" else BOOK_SECTIONS


def render(title: str, kind: str, meta_lines=None, body: dict | None = None) -> str:
    body = body or {}
    out = []
    if meta_lines:
        out += ["---"] + meta_lines + ["---", ""]
    out.append("# " + title)
    out.append("")
    out.append("> 条目格式：【确认·日期·\"原话\"】#id 正文 / 【待确认】#id 正文 / 【已失效·日期·被 #id 替代】#id 正文")
    out.append("")
    for i, (key, cn) in enumerate(sections_of(kind), 1):
        out.append("## %d. %s" % (i, cn))
        items = body.get(key) or []
        out += items if items else [PLACEHOLDER]
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def find_section_bounds(lines, title: str):
    head = None
    for i, ln in enumerate(lines):
        m = re.match(r"^##\s+\d+\.\s*(.+?)\s*$", ln)
        if not m:
            continue
        got = m.group(1)
        if got.startswith(title) or title in got:
            head = i
            break
    if head is None:
        return None
    insert = head + 1
    for j in range(head + 1, len(lines)):
        if lines[j].startswith("## "):
            break
        if lines[j].startswith("- "):
            insert = j + 1
        elif lines[j].strip() in (PLACEHOLDER, ""):
            continue
        else:
            insert = j + 1
    return head, insert


def insert_item(path: str, kind: str, key: str, item_line: str) -> bool:
    lines = read(path).splitlines()
    cn = dict(sections_of(kind))[key]
    bounds = find_section_bounds(lines, cn)
    if bounds is None:
        return False
    head, insert = bounds
    lines.insert(insert, item_line)
    j = head + 1
    while j < len(lines) and not lines[j].startswith("## "):
        if lines[j].strip() == PLACEHOLDER:
            lines.pop(j)
            continue
        j += 1
    write_atomic(path, "\n".join(lines) + "\n")
    return True


def count_items(path: str, kind: str) -> dict:
    lines = read(path).splitlines()
    result, cur = {}, None
    for ln in lines:
        if ln.startswith("## "):
            m = re.match(r"^##\s+\d+\.\s*(.+)$", ln)
            cur = m.group(1).strip() if m else None
            result[cur] = 0
        elif ln.startswith("- ") and cur:
            result[cur] += 1
    return result


def parse_items(path: str):
    """返回 [(行号, marker, id, 正文)]"""
    out = []
    for i, ln in enumerate(read(path).splitlines(), 1):
        m = ITEM_RE.match(ln)
        if m:
            out.append((i, m.group(1), m.group(2) or "", m.group(3).strip()))
    return out


def touch_updated(path: str) -> None:
    lines = read(path).splitlines()
    for i, ln in enumerate(lines[:15]):
        if ln.startswith("updated:"):
            lines[i] = 'updated: "%s"' % today()
            break
    write_atomic(path, "\n".join(lines) + "\n")


# ------------------------------------------------------------------ 路径
def card_dir(store: str, slug: str) -> str:
    return os.path.join(store, slug)


def main_path(store: str, slug: str) -> str:
    return os.path.join(card_dir(store, slug), MAIN_NAME)


def book_path(store: str, slug: str, book: str) -> str:
    return os.path.join(card_dir(store, slug), "books", slugify(book) + ".md")


def sess_path(store: str, slug: str) -> str:
    return os.path.join(card_dir(store, slug), "sessions.json")


def journal_dir(store: str, slug: str) -> str:
    return os.path.join(card_dir(store, slug), "journal")


def resolve(store: str, project: str | None, slug: str | None) -> str:
    if slug and os.path.isdir(card_dir(store, slug)):
        return slug
    if not project:
        fail("请用 --project 或 --slug 指定项目")
    hit = []
    for d in sorted(os.listdir(store)) if os.path.isdir(store) else []:
        p = os.path.join(store, d, MAIN_NAME)
        if not os.path.isfile(p):
            continue
        for ln in read(p).splitlines()[:12]:
            if ln.startswith("# "):
                if project in ln[2:].strip() or project in d:
                    hit.append(d)
                break
    if not hit:
        fail("没找到项目卡：%s。用 list 看看有哪些。" % project)
    if len(hit) > 1:
        fail("命中多张卡，请用 --slug 指定：" + "、".join(hit))
    return hit[0]


def list_books(store: str, slug: str):
    bdir = os.path.join(card_dir(store, slug), "books")
    if not os.path.isdir(bdir):
        return []
    return sorted(f[:-3] for f in os.listdir(bdir) if f.endswith(".md"))


def meta_workspaces(path: str):
    if not os.path.isfile(path):
        return []
    lines = read(path).splitlines()[:20]
    out = []
    for i, ln in enumerate(lines):
        if not ln.startswith("workspaces:"):
            continue
        val = ln.split(":", 1)[1].strip().strip('"')
        if val:
            out += [x.strip().strip('"') for x in val.split(";") if x.strip()]
        for nxt in lines[i + 1:]:
            s = nxt.strip()
            if s.startswith("- "):
                out.append(s[2:].strip().strip('"'))
            else:
                break
        break
    seen, uniq = set(), []
    for w in out:
        key = os.path.normcase(os.path.abspath(w)) if w else w
        if w and key not in seen:
            seen.add(key)
            uniq.append(w)
    return uniq


def add_workspace(store: str, slug: str, workspace: str) -> None:
    p = main_path(store, slug)
    ws = meta_workspaces(p)
    target = os.path.abspath(workspace)
    if any(os.path.normcase(os.path.abspath(w)) == os.path.normcase(target) for w in ws):
        return
    ws.append(target)
    lines = read(p).splitlines()
    for i, ln in enumerate(lines[:15]):
        if ln.startswith("workspaces:"):
            lines[i] = 'workspaces: "%s"' % ";".join(ws)
            break
    write_atomic(p, "\n".join(lines) + "\n")


# ------------------------------------------------------------------ 会话与事件
def sess_load(store: str, slug: str) -> dict:
    p = sess_path(store, slug)
    if not os.path.isfile(p):
        return {}
    try:
        return json.loads(read(p)) or {}
    except Exception:
        return {}


def sess_save(store: str, slug: str, data: dict) -> None:
    cutoff = now_dt() - timedelta(days=7)
    clean = {}
    for k, v in data.items():
        try:
            if datetime.strptime(v.get("beat", ""), "%Y-%m-%dT%H:%M:%S") >= cutoff:
                clean[k] = v
        except Exception:
            pass
    write_atomic(sess_path(store, slug), json.dumps(clean, ensure_ascii=False, indent=1))


def sess_touch(store: str, slug: str, sid: str, book: str | None, note: str | None,
               cwd: str | None = None) -> None:
    data = sess_load(store, slug)
    rec = data.get(sid) or {}
    rec.setdefault("since", now_iso())
    rec["beat"] = now_iso()
    rec["cwd"] = os.path.abspath(cwd or os.getcwd())
    if book:
        rec["book"] = book
    if note:
        rec["note"] = note
    data[sid] = rec
    sess_save(store, slug, data)


def journal_add(store: str, slug: str, rec: dict) -> None:
    d = journal_dir(store, slug)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, now_dt().strftime("%Y-%m") + ".ndjson")
    rec = dict(rec)
    rec.setdefault("t", now_iso())
    with open(p, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def journal_all(store: str, slug: str):
    """读事件流全量（最近三个月的文件）。Stop 守卫和 audit 都用它。"""
    files = sorted(glob.glob(os.path.join(journal_dir(store, slug), "*.ndjson")))[-3:]
    out = []
    for fp in files:
        try:
            for ln in read(fp).splitlines():
                ln = ln.strip()
                if ln:
                    out.append(json.loads(ln))
        except Exception:
            continue
    return out


def journal_tail(store: str, slug: str, n: int = 8):
    return journal_all(store, slug)[-n:]


def guard_log_path(store: str) -> str:
    """Stop 守卫的判定日志，放在卡片库根目录，不属于任何一张卡。"""
    return os.path.join(store, ".stop-guard.log")


def guard_read(store: str, n: int = 400):
    p = guard_log_path(store)
    if not os.path.isfile(p):
        return []
    try:
        return [json.loads(x) for x in read(p).splitlines() if x.strip()][-n:]
    except Exception:
        return []


def guard_write(store: str, rec: dict) -> None:
    """只追加，绝不因日志失败影响 hook。超过 2000 行收敛到 400 行。"""
    try:
        os.makedirs(store, exist_ok=True)
        p = guard_log_path(store)
        rec = dict(rec)
        rec.setdefault("t", now_iso())
        with open(p, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        if sum(1 for _ in open(p, encoding="utf-8", errors="replace")) > 2000:
            lines = open(p, encoding="utf-8", errors="replace").read().splitlines()
            write_atomic(p, "\n".join(lines[-400:]) + "\n")
    except Exception:
        pass


# ------------------------------------------------------------------ 备份
def backup(path: str) -> str:
    if not os.path.isfile(path):
        return ""
    root = os.path.dirname(os.path.dirname(path)) if os.path.basename(
        os.path.dirname(path)) == "books" else os.path.dirname(path)
    bdir = os.path.join(root, "backups")
    os.makedirs(bdir, exist_ok=True)
    content = read(path)
    latest = sorted(glob.glob(os.path.join(bdir, os.path.splitext(os.path.basename(path))[0] + ".*.md")))
    if latest:
        try:
            if read(latest[-1]) == content:
                return ""
        except Exception:
            pass
    ts = now_dt().strftime("%Y%m%d-%H%M%S-%f")[:-3]
    dst = os.path.join(bdir, "%s.%s.%d.md" % (
        os.path.splitext(os.path.basename(path))[0], ts, os.getpid()))
    shutil.copy2(path, dst)
    return os.path.basename(dst)


# ------------------------------------------------------------------ 校验
def validate_item(text: str, pending: bool, date: str) -> None:
    if not text.strip():
        fail("正文为空，拒绝写入")
    if not pending:
        try:
            if datetime.strptime(date, "%Y-%m-%d") > now_dt():
                fail("[F10] 日期在未来：%s" % date)
        except ValueError:
            fail("日期格式不对：%s（要 YYYY-MM-DD）" % date)
        for w in SPEC_WORDS:
            if w in text:
                fail("[F04] 标了确认却含推测词「%s」。要么改成 --pending，要么删掉推测表述。" % w)
    if CRED_PAT.search(text):
        fail("[F05] 疑似明文凭据。只记「凭据在哪」，不记值。")


def guard_section(kind: str, key: str, section_raw: str) -> None:
    valid = [k for k, _ in sections_of(kind)]
    if key in valid:
        return
    hint = "分册用：职责/口径/完成/待办/坑/位置" if kind == "book" else "主卡用：目标/口径/排除/完成/进度/待确认/位置"
    fail("「%s」不属于%s。%s" % (section_raw, "分册" if kind == "book" else "主卡", hint))


# ------------------------------------------------------------------ 命令
def cmd_init(a) -> None:
    slug = a.slug or slugify(a.project)
    cd = card_dir(a.store, slug)
    p = main_path(a.store, slug)
    if os.path.isfile(p) and not a.force:
        fail("[F09] 卡片已存在：%s（要覆盖加 --force，会先备份）" % slug)
    with card_lock(cd):
        if os.path.isfile(p):
            print("已备份：" + backup(p))
        meta = ["project: \"%s\"" % a.project, "slug: \"%s\"" % slug,
                "created: \"%s\"" % today(), "updated: \"%s\"" % today(),
                "status: \"active\"",
                "workspaces: \"%s\"" % (os.path.abspath(a.workspace) if a.workspace else "")]
        write_atomic(p, render("项目主卡 · " + a.project, "main", meta))
        for b in a.books or []:
            bp = book_path(a.store, slug, b)
            if not os.path.isfile(bp):
                write_atomic(bp, render("分册 · " + b, "book",
                                        ["project: \"%s\"" % a.project, "slug: \"%s\"" % slug,
                                         "book: \"%s\"" % slugify(b), "updated: \"%s\"" % today()]))
    print("✓ 主卡：%s" % p)
    if a.books:
        print("✓ 分册：" + "、".join(list_books(a.store, slug)))
    for m in refresh_all(a.store, slug, a.workspace):
        print("✓ 简报：%s" % m)


def cmd_add(a) -> None:
    slug = resolve(a.store, a.project, a.slug)
    key = ALIASES.get(a.section or "")
    if not key:
        fail("段名不认识：%s（可用：目标/口径/排除/完成/进度/待确认/位置/职责/待办/坑）" % a.section)
    kind = "book" if a.book else "main"
    guard_section(kind, key, a.section)
    date = a.date or today()
    validate_item(a.text, a.pending, date)

    target = book_path(a.store, slug, a.book) if a.book else main_path(a.store, slug)
    if not os.path.isfile(target):
        fail("目标不存在：%s（分册请先 card.py book --name %s）" % (target, a.book))

    item_id = new_id(a.text)
    marker = "【待确认】" if a.pending else '【确认·%s%s】' % (date, '·"%s"' % a.quote if a.quote else "")
    line = "- %s#%s %s" % (marker, item_id, a.text.strip())
    cd = card_dir(a.store, slug)

    with card_lock(cd):
        dupe = None
        new_text = a.text.strip()
        for _, mk, iid, body in parse_items(target):
            if mk.startswith("已失效"):
                continue
            old = body.strip()
            if old == new_text:
                dupe = (iid, body, 1.0)
                break
            if len(new_text) >= 12:
                r = difflib.SequenceMatcher(None, old, new_text).ratio()
                if r >= 0.93:
                    dupe = (iid, body, r)
                    break
        if dupe and not a.force:
            print("✗ [F06] 已有近似条目 #%s（相似度 %.0f%%）：%s" % (dupe[0], dupe[2] * 100, dupe[1][:40]))
            print("  真要继续，加 --force；要替换它，用 revise --id %s。" % dupe[0])
            sys.exit(2)

        print("备份：" + (backup(target) or "内容未变，跳过"))
        if not insert_item(target, kind, key, line):
            fail("没找到段「%s」，文件未改动" % dict(sections_of(kind))[key])

        if a.supersede:
            ok = mark_superseded(target, a.supersede, item_id)
            print(("✓ 旧条目 #%s 已标失效" % a.supersede) if ok else "⚠ 没找到 #%s，未标失效" % a.supersede)

        touch_updated(target)
        if target != main_path(a.store, slug):
            touch_updated(main_path(a.store, slug))

        sess_touch(a.store, slug, a.session or worktag(), a.book or "main",
                   "刚记了一条：%s" % a.text.strip()[:24], cwd=a.workspace)
        journal_add(a.store, slug, {
            "w": a.session or worktag(), "a": "add",
            "b": a.book or "主卡", "sec": dict(sections_of(kind))[key],
            "id": item_id, "text": a.text.strip()[:80]})
        cnt = count_items(target, kind)

    print("✓ 已写入 %s / %s · #%s" % ("分册 " + slugify(a.book) if a.book else "主卡",
                                     dict(sections_of(kind))[key], item_id))
    print("✓ 当前：" + " · ".join("%s %d" % (k, v) for k, v in cnt.items() if v))
    for m in refresh_all(a.store, slug, a.workspace):
        print("✓ 简报：%s" % m)


def mark_superseded(path: str, old_id: str, new_id_: str) -> bool:
    lines = read(path).splitlines()
    for i, ln in enumerate(lines):
        m = ITEM_RE.match(ln)
        if not m or m.group(2) != old_id:
            continue
        body = m.group(3).strip()
        lines[i] = "- 【已失效·%s·被 #%s 替代】#%s %s" % (today(), new_id_, old_id, body)
        write_atomic(path, "\n".join(lines) + "\n")
        return True
    return False


def cmd_revise(a) -> None:
    slug = resolve(a.store, a.project, a.slug)
    target = book_path(a.store, slug, a.book) if a.book else main_path(a.store, slug)
    if not os.path.isfile(target):
        fail("不存在：%s" % target)
    kind = "book" if a.book else "main"
    hits = [(ln, mk, iid, body) for ln, mk, iid, body in parse_items(target) if iid == a.id]
    if not hits:
        fail("没找到条目 #%s（用 search 或 show 查 id）" % a.id)
    ln, mk, iid, body = hits[0]
    text = (a.text or "").strip()
    if not text:
        fail("--text 不能为空")
    new_id_ = new_id(text)

    cd = card_dir(a.store, slug)
    with card_lock(cd):
        print("备份：" + (backup(target) or "内容未变，跳过"))
        lines = read(target).splitlines()
        marker = "【待确认】" if a.pending else '【确认·%s】' % today()
        lines[ln - 1] = "- 【已失效·%s·被 #%s 替代】#%s %s" % (today(), new_id_, iid, body)
        lines.insert(ln, "- %s#%s %s" % (marker, new_id_, text))
        write_atomic(target, "\n".join(lines) + "\n")
        touch_updated(target)
        sess_touch(a.store, slug, a.session or worktag(), a.book or "main",
                   "改了一条：%s" % text[:24], cwd=a.workspace)
        journal_add(a.store, slug, {
            "w": a.session or worktag(), "a": "revise", "b": a.book or "主卡",
            "sec": "改", "id": new_id_, "text": text[:80], "old": iid})
    print("✓ #%s 已作废，#%s 已写入" % (iid, new_id_))


def cmd_claim(a) -> None:
    slug = resolve(a.store, a.project, a.slug)
    sid = a.session or worktag()
    book = a.book or "main"
    cd = card_dir(a.store, slug)
    with card_lock(cd):
        data = sess_load(a.store, slug)
        others = [k for k, v in data.items()
                  if k != sid and v.get("book") == book
                  and (now_dt() - datetime.strptime(v.get("beat", "1970-01-01T00:00:00"),
                                                    "%Y-%m-%dT%H:%M:%S")).total_seconds() < STALE_SESSION_MIN * 60]
        sess_save(a.store, slug, data)  # 顺手清过期
        sess_touch(a.store, slug, sid, book, a.note or "占了这个工作面", cwd=a.workspace)
        journal_add(a.store, slug, {"w": sid, "a": "claim", "b": book, "sec": "占",
                                    "text": a.note or ""})
    print("✓ 已登记：%s → %s" % (sid, book))
    if a.note:
        print("  在干什么：" + a.note)
    if others:
        print("⚠ 同一工作面还有 " + "、".join(others) + " 在跑，改动前先看 resume")


def cmd_release(a) -> None:
    slug = resolve(a.store, a.project, a.slug)
    sid = a.session or worktag()
    with card_lock(card_dir(a.store, slug)):
        data = sess_load(a.store, slug)
        if sid in data:
            data.pop(sid)
            sess_save(a.store, slug, data)
            journal_add(a.store, slug, {"w": sid, "a": "release", "b": a.book or "", "sec": "放", "text": ""})
            print("✓ 已释放：" + sid)
        else:
            print("· 没有登记记录：" + sid)


def cmd_resume(a) -> None:
    slug = resolve(a.store, a.project, a.slug)
    mp = main_path(a.store, slug)
    cwd = os.path.abspath(a.workspace or os.getcwd())
    sid = a.session or worktag(cwd)
    # 读过卡留痕：Stop 守卫与 audit 靠它知道「这个会话碰过卡片」。
    # 只追加事件流，不改卡片内容，也不登记 sessions.json（不制造虚假占用）。
    journal_add(a.store, slug, {
        "w": sid, "a": "open", "b": "", "sec": "读",
        "cwd": cwd, "text": "开工读了卡"})
    text = read(mp)
    upd = ""
    for ln in text.splitlines()[:12]:
        if ln.startswith("updated:"):
            upd = ln.split(":", 1)[1].strip().strip('"')
    print("=== %s · %s ===" % (slug, ("更新于 " + upd) if upd else "日期未记录"))
    if upd:
        try:
            days = (now_dt() - datetime.strptime(upd, "%Y-%m-%d")).days
            if days > a.stale_days:
                print("⚠ 已 %d 天未更新，续用前先核对口径" % days)
        except Exception:
            pass

    data = sess_load(a.store, slug)
    live, dead = [], []
    for sid, v in data.items():
        try:
            gap = (now_dt() - datetime.strptime(v.get("beat", ""), "%Y-%m-%dT%H:%M:%S")).total_seconds() / 60
        except Exception:
            continue
        (live if gap < STALE_SESSION_MIN else dead).append((sid, v, gap))

    if live:
        print("\n▌正在做什么")
        for sid, v, gap in sorted(live, key=lambda x: x[2])[:5]:
            print("  · %s  %s  %s  %s" % (sid, alias_of(v.get("cwd", "")),
                                          human_ago(v.get("beat", "")),
                                          (v.get("note") or "")[:28]))
    if dead:
        print("\n▌可能已结束（%d 个，超过 %d 分钟没动静）" % (len(dead), STALE_SESSION_MIN))

    tail = [r for r in journal_all(a.store, slug)
            if r.get("a") in ("add", "revise", "claim", "release")][-6:]
    if tail:
        print("\n▌最近发生")
        for r in tail:
            t = r.get("t", "")[11:16]
            print("  %s %-6s [%s/%s] %s" % (t, r.get("w", "")[:6], r.get("b", ""),
                                            r.get("sec", ""), (r.get("text") or "")[:34]))

    books = list_books(a.store, slug)
    if books:
        print("\n▌待办")
        row = []
        for b in books:
            cnt = count_items(book_path(a.store, slug, b), "book")
            todo = cnt.get("待办", 0)
            pit = cnt.get("踩过的坑", 0)
            row.append("%s %d（坑 %d）" % (b, todo, pit))
        print("  " + " · ".join(row))

    opens = [body for _, mk, _, body in parse_items(mp) if mk.startswith("待确认")]
    if opens:
        print("\n▌待确认（%d）" % len(opens))
        for x in opens[:3]:
            print("  · " + x[:40])
        if len(opens) > 3:
            print("  …还有 %d 条" % (len(opens) - 3))

    cons = count_items(mp, "main").get("口径与约束", 0)
    invalid = len([1 for _, mk, _, _ in parse_items(mp) if mk.startswith("已失效")])
    print("\n▌口径 %d 条%s" % (cons, ("，其中 %d 条已失效" % invalid) if invalid else ""))
    print("细节：show --book <名> ｜ 查旧事：search 关键词" + (" ｜ 全量：--full" if not a.full else ""))

    if a.full:
        print("\n" + "-" * 40)
        print(text)


def cmd_show(a) -> None:
    slug = resolve(a.store, a.project, a.slug)
    p = book_path(a.store, slug, a.book) if a.book else main_path(a.store, slug)
    if not os.path.isfile(p):
        fail("不存在：%s" % p)
    print(read(p))


def cmd_search(a) -> None:
    slug = resolve(a.store, a.project, a.slug)
    kw = (a.keyword or "").lower()
    if not kw:
        fail("给个关键词：search 扑克")
    targets = [("主卡", main_path(a.store, slug))] + \
              [("分册 " + b, book_path(a.store, slug, b)) for b in list_books(a.store, slug)]
    if a.book:
        targets = [("分册 " + slugify(a.book), book_path(a.store, slug, a.book))]
    hits = 0
    for name, p in targets:
        if not os.path.isfile(p):
            continue
        cur = ""
        for i, ln in enumerate(read(p).splitlines(), 1):
            if ln.startswith("## "):
                cur = ln.lstrip("# ").strip()
            if kw in ln.lower():
                hits += 1
                print("%s:%d [%s] %s" % (name, i, cur, ln.strip()[:100]))
    js = [r for r in journal_tail(a.store, slug, 400) if kw in json.dumps(r, ensure_ascii=False).lower()]
    for r in js[-5:]:
        hits += 1
        print("事件流 %s [%s] %s" % (r.get("t", "")[:16], r.get("b", ""), (r.get("text") or "")[:60]))
    print("— 命中 %d 处" % hits)


def cmd_check(a) -> None:
    slug = resolve(a.store, a.project, a.slug)
    problems, notes = [], []
    all_ids = set()
    for p, kind in [(main_path(a.store, slug), "main")] + \
                   [(book_path(a.store, slug, b), "book") for b in list_books(a.store, slug)]:
        for i, ln in enumerate(read(p).splitlines(), 1):
            if not ln.startswith("- ") or ln.strip() == "-":
                continue
            m = ITEM_RE.match(ln)
            if not m:
                problems.append("[F03] %s:%d 条目缺标记：%s" % (os.path.basename(p), i, ln[:40]))
                continue
            mk, iid, body = m.group(1), m.group(2) or "", m.group(3)
            if iid:
                all_ids.add(iid)
            if CRED_PAT.search(ln):
                problems.append("[F05] %s:%d 疑似明文凭据" % (os.path.basename(p), i))
            if mk.startswith("确认"):
                if not DATE_RE.search(mk):
                    problems.append("[F03] %s:%d 确认项缺日期" % (os.path.basename(p), i))
                else:
                    d = DATE_RE.search(mk).group(0)
                    try:
                        if datetime.strptime(d, "%Y-%m-%d") > now_dt():
                            problems.append("[F10] %s:%d 日期在未来：%s" % (os.path.basename(p), i, d))
                    except Exception:
                        pass
                for w in SPEC_WORDS:
                    if w in body:
                        problems.append("[F04] %s:%d 确认项含推测词「%s」" % (os.path.basename(p), i, w))
    for p in [main_path(a.store, slug)] + [book_path(a.store, slug, b) for b in list_books(a.store, slug)]:
        for i, ln in enumerate(read(p).splitlines(), 1):
            m = ITEM_RE.match(ln)
            if m and m.group(1).startswith("已失效"):
                ref = re.search(r"被\s*#([0-9a-f]{4,8})", m.group(1))
                if ref and ref.group(1) not in all_ids:
                    problems.append("[F11] %s:%d 失效引用指向不存在的 #%s" % (
                        os.path.basename(p), i, ref.group(1)))
    for b in list_books(a.store, slug):
        got = set(re.sub(r"^##\s+\d+\.\s*", "", ln).strip()
                  for ln in read(book_path(a.store, slug, b)).splitlines() if ln.startswith("## "))
        missing = [cn for _, cn in BOOK_SECTIONS if cn not in got]
        if missing:
            problems.append("[F12] 分册 %s 缺段：%s" % (b, "、".join(missing)))
    for sid, v in sess_load(a.store, slug).items():
        try:
            gap = (now_dt() - datetime.strptime(v.get("beat", ""), "%Y-%m-%dT%H:%M:%S")).total_seconds() / 60
            if gap >= STALE_SESSION_MIN:
                notes.append("会话 %s 超过 %d 分钟无心跳（%s）" % (sid, STALE_SESSION_MIN, v.get("note", "")[:20]))
        except Exception:
            pass
    if problems:
        print("✗ 发现 %d 个问题：" % len(problems))
        for x in problems:
            print("  " + x)
        sys.exit(1)
    print("✓ 体检通过：主卡 + %d 个分册，%d 条记录" % (len(list_books(a.store, slug)), len(all_ids)))
    for n in notes:
        print("  · " + n)


def cmd_list(a) -> None:
    if not os.path.isdir(a.store):
        print("卡片库为空：%s" % a.store)
        return
    found = False
    for d in sorted(os.listdir(a.store)):
        p = os.path.join(a.store, d, MAIN_NAME)
        if os.path.isfile(p):
            found = True
            title = ""
            for ln in read(p).splitlines()[:12]:
                if ln.startswith("# "):
                    title = ln[2:].strip()
                    break
            print("· %-14s %-22s %d 个分册" % (d, title[:22], len(list_books(a.store, d))))
    if not found:
        print("卡片库为空：%s" % a.store)


def cmd_book(a) -> None:
    slug = resolve(a.store, a.project, a.slug)
    if not a.name:
        bs = list_books(a.store, slug)
        print("分册：" + ("、".join(bs) if bs else "无"))
        return
    bp = book_path(a.store, slug, a.name)
    if os.path.isfile(bp):
        fail("分册已存在：%s" % bp)
    with card_lock(card_dir(a.store, slug)):
        write_atomic(bp, render("分册 · " + a.name, "book",
                                ["slug: \"%s\"" % slug, "book: \"%s\"" % slugify(a.name),
                                 "updated: \"%s\"" % today()]))
    print("✓ 新分册：%s" % bp)


def cmd_gc(a) -> None:
    slug = resolve(a.store, a.project, a.slug)
    cd = card_dir(a.store, slug)
    bdir = os.path.join(cd, "backups")
    removed = 0
    if os.path.isdir(bdir):
        files = sorted(glob.glob(os.path.join(bdir, "*.md")), key=os.path.getmtime)
        if len(files) > a.keep:
            for f in files[:-a.keep]:
                os.remove(f)
                removed += 1
    arch = os.path.join(journal_dir(a.store, slug), "archive")
    moved = 0
    cutoff = (now_dt() - timedelta(days=120)).strftime("%Y-%m")
    for f in glob.glob(os.path.join(journal_dir(a.store, slug), "*.ndjson")):
        if os.path.basename(f)[:7] < cutoff:
            os.makedirs(arch, exist_ok=True)
            shutil.move(f, os.path.join(arch, os.path.basename(f)))
            moved += 1
    print("✓ 清理备份 %d 个（保留最近 %d）｜归档事件流 %d 个" % (removed, a.keep, moved))


def grab_section(path: str, title_keys: tuple, limit: int = 3, width: int = 100) -> list:
    """从卡文件抓指定 section 的条目正文（去 marker、截断），供简报置顶。
    找不到该 section 或条目为空返回 []。只读，不改文件。"""
    if not os.path.isfile(path):
        return []
    out, cur = [], False
    for ln in read(path).splitlines():
        if ln.startswith("## "):
            m = re.match(r"^##\s+\d+\.\s*(.+)$", ln)
            t = m.group(1).strip() if m else ""
            cur = any(k in t for k in title_keys)
            continue
        if cur and ln.startswith("- "):
            body = ITEM_RE.match(ln.strip())
            text = (body.group(3) if body else ln.strip()[2:]).strip()
            if text and text != "_（暂无记录）_":
                out.append(text[:width])
                if len(out) >= limit:
                    break
    return out


def refresh_mirror(store: str, slug: str, workspace: str) -> str:
    mp = main_path(store, slug)
    books = list_books(store, slug)
    # 开工先读：主卡已排除方案 + 各分册踩过的坑，置顶抽取（坑不 resume 就看不见 = 白记）
    warn = []
    for t in grab_section(mp, ("已排除", "排除"), 3):
        warn.append("[主卡·排除] " + t)
    for b in books:
        for t in grab_section(book_path(store, slug, b), ("坑",), 2):
            warn.append("[%s·坑] %s" % (b, t))
    add = ["", "---", "", "> 这是自动生成的简报，只读。要改卡请让我用 card.py，不要手改本文件。", ""]
    if warn:
        add += ["## ⚠ 开工先读：坑与已排除方案", ""]
        add += ["- " + w for w in warn[:6]]
        add += [""]
    add += ["## 分册索引", ""]
    if books:
        for b in books:
            cnt = count_items(book_path(store, slug, b), "book")
            add.append("- `%s` —— 待办 %d · 踩过的坑 %d" % (b, cnt.get("待办", 0), cnt.get("踩过的坑", 0)))
    else:
        add.append("_（暂无分册）_")
    dst = os.path.join(os.path.abspath(workspace), MIRROR_REL)
    write_atomic(dst, read(mp).rstrip() + "\n" + "\n".join(add) + "\n")
    return dst


def refresh_all(store: str, slug: str, workspace: str | None):
    targets = [workspace] if workspace else meta_workspaces(main_path(store, slug))
    done = []
    for w in targets:
        try:
            done.append(refresh_mirror(store, slug, w))
        except Exception as e:
            print("⚠ 简报刷新失败（%s）：%s" % (w, e))
    if not targets:
        print("· 这张卡还没绑定工作区，简报未生成（init/claim 时加 --workspace 即可）")
    return done


def cmd_mirror(a) -> None:
    slug = resolve(a.store, a.project, a.slug)
    for m in refresh_all(a.store, slug, a.workspace):
        print("✓ 简报：%s" % m)


def cmd_audit(a) -> None:
    """查漏：谁读过卡却没写卡；Stop 守卫拦了几次、有没有补上。"""
    if a.slug and os.path.isdir(card_dir(a.store, a.slug)):
        slugs = [a.slug]
    else:
        slugs = sorted(d for d in (os.listdir(a.store) if os.path.isdir(a.store) else [])
                       if os.path.isfile(main_path(a.store, d)))
    if not slugs:
        print("· 没有卡片")
        return
    cutoff = (now_dt() - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S")
    print("=== 卡片查漏（最近 7 天）===")
    missed_all = 0
    for slug in slugs:
        rows = [r for r in journal_all(a.store, slug) if r.get("t", "") >= cutoff]
        opens, writes = {}, set()
        for r in rows:
            w, act = r.get("w", ""), r.get("a")
            if act == "open":
                rec = opens.setdefault(w, {"n": 0, "t": r.get("t", ""), "cwd": r.get("cwd", "")})
                rec["n"] += 1
                rec["t"] = max(rec["t"], r.get("t", ""))
            elif act in ("add", "revise", "claim"):
                writes.add(w)
        pending = [(w, v) for w, v in opens.items() if w not in writes]
        g = [x for x in guard_read(a.store)
             if x.get("slug") == slug and x.get("t", "") >= cutoff]
        blocked = [x for x in g if x.get("k") == "block"]
        missed = [x for x in g if x.get("k") == "miss"]
        missed_all += len(missed)
        if not pending and not blocked and not missed:
            print("  ✓ %s：没有漏记" % slug)
            continue
        print("  · %s" % slug)
        for w, v in sorted(pending, key=lambda x: x[1]["t"], reverse=True)[:5]:
            print("      读过没写  %s  %s  %s（读 %d 次）" % (
                w, alias_of(v["cwd"]), v["t"][:16], v["n"]))
        if blocked or missed:
            print("      Stop 拦截 %d 次，提醒后仍未补卡 %d 次" % (len(blocked), len(missed)))
            for x in missed[-3:]:
                print("      漏记 %s  %s" % (x.get("t", "")[:16], str(x.get("sid", ""))[:8]))
    print("— 共 %d 张卡；提醒后仍未补卡 %d 次" % (len(slugs), missed_all))
    print("  守卫总开关：%s（文件存在即停止拦截）" % os.path.join(a.store, ".stop-guard-off"))


def main() -> None:
    ap = argparse.ArgumentParser(description="我的项目卡片 2.0")
    ap.add_argument("cmd", choices=["init", "add", "revise", "claim", "release", "resume",
                                    "show", "search", "check", "list", "book", "mirror",
                                    "gc", "audit"])
    ap.add_argument("--project")
    ap.add_argument("--slug")
    ap.add_argument("--store", default=DEFAULT_STORE)
    ap.add_argument("--workspace", default=None)
    ap.add_argument("--book")
    ap.add_argument("--books", nargs="*")
    ap.add_argument("--name")
    ap.add_argument("--section")
    ap.add_argument("--text")
    ap.add_argument("--quote")
    ap.add_argument("--date")
    ap.add_argument("--id")
    ap.add_argument("--keyword")
    ap.add_argument("--session")
    ap.add_argument("--note")
    ap.add_argument("--supersede")
    ap.add_argument("--pending", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--keep", type=int, default=40)
    ap.add_argument("--stale-days", type=int, default=14)
    a = ap.parse_args()
    {"init": cmd_init, "add": cmd_add, "revise": cmd_revise, "claim": cmd_claim,
     "release": cmd_release, "resume": cmd_resume, "show": cmd_show, "search": cmd_search,
     "check": cmd_check, "list": cmd_list, "book": cmd_book, "mirror": cmd_mirror,
     "gc": cmd_gc, "audit": cmd_audit}[a.cmd](a)


if __name__ == "__main__":
    main()
