#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""我的项目卡片 · 引擎

设计目标（相对旧版的三处改进）：
  1. 一次调用做完全部：备份 → 写入 → 校验 → 刷新镜像 → 打印结果。不再需要 read last-report.txt。
  2. 主卡 + 分册：主卡只放跨工作面通用的内容；每个工作面一个分册，改一个不碰其它。
  3. 输出直接可读：所有结果打到 stdout，失败即以非 0 退出并保持文件原样。

命令：
  init    建卡（主卡 + 可选分册）
  add     追加一条（--book 指定写哪个分册）
  resume  读卡简报（只读）
  check   体检
  list    列卡
  book    新建/列出分册
  mirror  只刷新工作区镜像
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HOME = os.path.expanduser("~")
DEFAULT_STORE = os.path.join(HOME, ".workbuddy", "projects")
MAIN_NAME = "context-card.md"
MIRROR_REL = os.path.join(".workbuddy", "PROJECT_CONTEXT.md")

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
}

SPEC_WORDS = ["应该", "可能是", "大概", "估计", "也许是", "我猜", "猜测",
              "或许是", "看上去像", "八成", "感觉是", "大概率"]
CRED_PAT = re.compile(
    r"(password|passwd|pwd|token|secret|api[_-]?key|access[_-]?key|private[_-]?key"
    r"|密码|口令|密钥|私钥|秘钥|令牌|连接串)\s*[:=＝:]\s*\S+", re.I)
ITEM_RE = re.compile(r"^-\s+【([^】]*)】\s*(.*)$")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def slugify(name: str) -> str:
    s = re.sub(r"[\\/:*?\"<>|\s]+", "-", name.strip())
    s = re.sub(r"-+", "-", s).strip("-")
    return (s or "p" + datetime.now().strftime("%Y%m%d%H%M%S"))[:60]


def read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def meta_workspaces(path: str):
    """读主卡 frontmatter 里登记的工作区。

    兼容两种写法：
      workspaces: "a;b"      （本引擎写入的单行式）
      workspaces:\\n  - "a"  （旧引擎写入的 YAML 列表式）
    """
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
            elif s == "" or s.startswith("---"):
                break
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


def refresh_all(store: str, slug: str, workspace: str | None):
    """刷新镜像：显式给了工作区就只刷它，否则刷主卡里登记过的全部。"""
    targets = [workspace] if workspace else meta_workspaces(main_path(store, slug))
    done = []
    for w in targets:
        try:
            done.append(refresh_mirror(store, slug, w))
        except Exception as e:
            print("⚠ 镜像刷新失败（%s）：%s" % (w, e))
    return done


def backup(path: str) -> str:
    if not os.path.isfile(path):
        return ""
    bdir = os.path.join(os.path.dirname(path), "backups")
    os.makedirs(bdir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = os.path.join(bdir, "%s.%s%s" % (
        os.path.splitext(os.path.basename(path))[0], ts, os.path.splitext(path)[1]))
    shutil.copy2(path, dst)
    return os.path.basename(dst)


def fail(msg: str) -> None:
    print("✗ " + msg)
    sys.exit(1)


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
    out.append("> 每条必须带【确认·日期·\"原话\"】或【待确认】；标待确认的不当结论用。")
    out.append("")
    for i, (key, cn) in enumerate(sections_of(kind), 1):
        out.append("## %d. %s" % (i, cn))
        items = body.get(key) or []
        if items:
            out += items
        else:
            out.append("_（暂无记录）_")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def find_section_bounds(lines, title: str):
    """返回 (标题行号, 插入点行号)；找不到返回 None。

    标题匹配用宽松规则：文件里的段名以规范名开头，或包含规范名，都算命中。
    这样旧卡沿用「已完成步骤 / 关键位置与文件 / 待确认事项」这类名字也能继续用。
    """
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
        elif lines[j].strip() == "_（暂无记录）_" or lines[j].strip() == "":
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
    _, insert = bounds
    if lines[insert - 1].strip() == "_（暂无记录）_" if insert - 1 < len(lines) else False:
        lines.pop(insert - 1)
        insert -= 1
    lines.insert(insert, item_line)
    write(path, "\n".join(lines) + "\n")
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


# ------------------------------------------------------------------ 校验
def validate_item(text: str, pending: bool, date: str) -> None:
    if not text.strip():
        fail("正文为空，拒绝写入")
    if not pending:
        future = False
        try:
            future = datetime.strptime(date, "%Y-%m-%d") > datetime.now()
        except Exception:
            fail("日期格式不对：%s（要 YYYY-MM-DD）" % date)
        if future:
            fail("[F10] 日期在未来：%s" % date)
        for w in SPEC_WORDS:
            if w in text:
                fail("[F04] 标了确认却含推测词「%s」。要么改成 --pending，要么删掉推测表述。" % w)
    if CRED_PAT.search(text):
        fail("[F05] 疑似明文凭据。只记「凭据在哪」，不记值。")


# ------------------------------------------------------------------ 路径
def card_dir(store: str, slug: str) -> str:
    return os.path.join(store, slug)


def main_path(store: str, slug: str) -> str:
    return os.path.join(card_dir(store, slug), MAIN_NAME)


def book_path(store: str, slug: str, book: str) -> str:
    return os.path.join(card_dir(store, slug), "books", slugify(book) + ".md")


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
        first = read(p).splitlines()[:12]
        for ln in first:
            if ln.startswith("# "):
                title = ln[2:].strip()
                if project in title or project in d:
                    hit.append(d)
                break
    if not hit:
        fail("没找到项目卡：%s。用 list 看看有哪些。" % project)
    if len(hit) > 1:
        fail("命中多张卡，请用 --slug 指定：" + "、".join(hit))
    return hit[0]


def refresh_mirror(store: str, slug: str, workspace: str) -> str:
    src = main_path(store, slug)
    text = read(src)
    books = list_books(store, slug)
    add = ["", "---", "", "## 分册索引（细节在各分册，主卡不重复）", ""]
    if books:
        for b in books:
            bp = book_path(store, slug, b)
            cnt = count_items(bp, "book")
            todo = cnt.get("待办", 0)
            add.append("- `%s` —— 职责 / 口径 / 已完成 / 待办 %d 条 / 位置" % (b, todo))
    else:
        add.append("_（暂无分册）_")
    dst = os.path.join(os.path.abspath(workspace), MIRROR_REL)
    write(dst, text.rstrip() + "\n" + "\n".join(add) + "\n")
    return dst


def list_books(store: str, slug: str):
    bdir = os.path.join(card_dir(store, slug), "books")
    if not os.path.isdir(bdir):
        return []
    return sorted(f[:-3] for f in os.listdir(bdir) if f.endswith(".md"))


# ------------------------------------------------------------------ 命令
def cmd_init(a) -> None:
    slug = a.slug or slugify(a.project)
    p = main_path(a.store, slug)
    if os.path.isfile(p) and not a.force:
        fail("[F09] 卡片已存在：%s（要覆盖加 --force，会先备份）" % slug)
    if os.path.isfile(p):
        print("已备份：" + backup(p))
    meta = ["project: \"%s\"" % a.project, "slug: \"%s\"" % slug,
            "created: \"%s\"" % today(), "updated: \"%s\"" % today(),
            "status: \"active\"",
            "workspaces: \"%s\"" % (os.path.abspath(a.workspace) if a.workspace else "")]
    write(p, render("项目主卡 · " + a.project, "main", meta))
    for b in a.books or []:
        bp = book_path(a.store, slug, b)
        if not os.path.isfile(bp):
            write(bp, render("分册 · " + b, "book",
                             ["project: \"%s\"" % a.project, "slug: \"%s\"" % slug,
                              "book: \"%s\"" % slugify(b), "updated: \"%s\"" % today()]))
    print("✓ 主卡：%s" % p)
    if a.books:
        print("✓ 分册：" + "、".join(list_books(a.store, slug)))
    for m in refresh_all(a.store, slug, a.workspace):
        print("✓ 镜像：%s" % m)


def cmd_add(a) -> None:
    slug = resolve(a.store, a.project, a.slug)
    key = ALIASES.get(a.section)
    if not key:
        fail("段名不认识：%s（可用：目标/口径/排除/完成/进度/待确认/位置/职责/待办）" % a.section)
    kind = "book" if a.book else "main"
    valid_keys = [k for k, _ in sections_of(kind)]
    if key not in valid_keys:
        hint = "分册用：职责/口径/完成/待办/位置" if kind == "book" else "主卡用：目标/口径/排除/完成/进度/待确认/位置"
        fail("「%s」不属于%s。%s" % (a.section, "分册" if a.book else "主卡", hint))
    date = a.date or today()
    validate_item(a.text, a.pending, date)
    target = book_path(a.store, slug, a.book) if a.book else main_path(a.store, slug)
    if not os.path.isfile(target):
        fail("目标不存在：%s（分册请先 card.py book --name %s）" % (target, a.book))
    marker = "【待确认】" if a.pending else '【确认·%s%s】' % (date, '·"%s"' % a.quote if a.quote else "")
    line = "- %s%s" % (marker, a.text.strip())
    print("备份：" + backup(target))
    if not insert_item(target, kind, key, line):
        fail("没找到段「%s」，文件未改动" % dict(sections_of(kind))[key])
    cnt = count_items(target, kind)
    print("✓ 已写入 %s / %s" % ("分册 " + slugify(a.book) if a.book else "主卡", dict(sections_of(kind))[key]))
    print("✓ 当前：" + " · ".join("%s %d" % (k, v) for k, v in cnt.items() if v))
    for m in refresh_all(a.store, slug, a.workspace):
        print("✓ 镜像：%s" % m)


def cmd_resume(a) -> None:
    slug = resolve(a.store, a.project, a.slug)
    p = main_path(a.store, slug)
    text = read(p)
    upd = ""
    for ln in text.splitlines()[:12]:
        if ln.startswith("updated:"):
            upd = ln.split(":", 1)[1].strip().strip('"')
    days = -1
    try:
        days = (datetime.now() - datetime.strptime(upd, "%Y-%m-%d")).days
    except Exception:
        pass
    print("=== 项目主卡 · %s ===" % slug)
    print("更新于 %s（%s）" % (upd or "?", ("距今 %d 天" % days) if days >= 0 else "日期未记录"))
    if days > a.stale_days:
        print("⚠ 已超过 %d 天未更新，续用前请先核对口径" % a.stale_days)
    cur = None
    for ln in text.splitlines():
        if ln.startswith("## "):
            cur = re.sub(r"^##\s+\d+\.\s*", "", ln).strip()
            print("\n【%s】" % cur)
        elif ln.startswith("- "):
            print("  " + ln)
    books = list_books(a.store, slug)
    if books:
        print("\n=== 分册 ===")
        for b in books:
            bp = book_path(a.store, slug, b)
            cnt = count_items(bp, "book")
            todo = cnt.get("待办", 0)
            print("· %-14s 待办 %d 条｜共 %d 条" % (b, todo, sum(cnt.values())))
        print("\n需要某册细节：" + " / ".join("card.py show --book " + b for b in books[:3]))


def cmd_show(a) -> None:
    slug = resolve(a.store, a.project, a.slug)
    p = book_path(a.store, slug, a.book) if a.book else main_path(a.store, slug)
    if not os.path.isfile(p):
        fail("不存在：%s" % p)
    print(read(p))


def cmd_check(a) -> None:
    slug = resolve(a.store, a.project, a.slug)
    problems = []
    for p, kind in [(main_path(a.store, slug), "main")] + \
                   [(book_path(a.store, slug, b), "book") for b in list_books(a.store, slug)]:
        for i, ln in enumerate(read(p).splitlines(), 1):
            if not ln.startswith("- ") or ln.strip() == "-":
                continue
            if not ITEM_RE.match(ln):
                problems.append("[F03] %s:%d 条目缺标记：%s" % (os.path.basename(p), i, ln[:40]))
            if CRED_PAT.search(ln):
                problems.append("[F05] %s:%d 疑似明文凭据" % (os.path.basename(p), i))
            m = ITEM_RE.match(ln)
            if m and m.group(1).startswith("确认"):
                if not DATE_RE.search(m.group(1)):
                    problems.append("[F03] %s:%d 确认项缺日期" % (os.path.basename(p), i))
                for w in SPEC_WORDS:
                    if w in m.group(2):
                        problems.append("[F04] %s:%d 确认项含推测词「%s」" % (os.path.basename(p), i, w))
    if problems:
        print("✗ 发现 %d 个问题：" % len(problems))
        for x in problems:
            print("  " + x)
        sys.exit(1)
    print("✓ 体检通过：主卡 + %d 个分册，无问题" % len(list_books(a.store, slug)))


def cmd_list(a) -> None:
    if not os.path.isdir(a.store):
        print("卡片库为空：%s" % a.store)
        return
    found = False
    for d in sorted(os.listdir(a.store)):
        p = os.path.join(a.store, d, MAIN_NAME)
        if os.path.isfile(p):
            found = True
            print("· %-18s %d 个分册" % (d, len(list_books(a.store, d))))
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
    write(bp, render("分册 · " + a.name, "book",
                     ["slug: \"%s\"" % slug, "book: \"%s\"" % slugify(a.name),
                      "updated: \"%s\"" % today()]))
    print("✓ 新分册：%s" % bp)


def cmd_mirror(a) -> None:
    slug = resolve(a.store, a.project, a.slug)
    for m in refresh_all(a.store, slug, a.workspace):
        print("✓ 镜像：%s" % m)


def main() -> None:
    ap = argparse.ArgumentParser(description="我的项目卡片")
    ap.add_argument("cmd", choices=["init", "add", "resume", "show", "check", "list", "book", "mirror"])
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
    ap.add_argument("--pending", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--stale-days", type=int, default=14)
    a = ap.parse_args()
    {"init": cmd_init, "add": cmd_add, "resume": cmd_resume, "show": cmd_show,
     "check": cmd_check, "list": cmd_list, "book": cmd_book, "mirror": cmd_mirror}[a.cmd](a)


if __name__ == "__main__":
    main()
