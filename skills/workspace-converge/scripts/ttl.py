#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""workspace-converge · 隔离区到期清理（TTL）

设计要点（v1.6.0）：
- 归档时写 _TTL.json：归档时间、到期时间、每个文件的 sha256 与处置类别。
  不靠目录 mtime / 目录名——copy、mv 会让时间戳失真。
- 只删「垃圾类」白名单命中的文件；记忆快照、旧日志、技能备份、交付物、
  基线/构建产物、仓库资产一律 pinned，永不自动删。
- 删除前查引用（各空间 MEMORY.md / 日志 / 自动化 prompt 导出文本）。
- 首次启用强制 dry-run（写 armed 标记），第二次起才真正 purge。
- 每次删除写 ledger（时间戳 / 原路径 / sha256 / 理由），重复运行幂等。
- 输出统一走 stdout.buffer 显式 UTF-8（Windows 管道默认 cp936 会乱码）。

只依赖标准库。所有写操作都限定在传入的空间根之内。
"""
import argparse
import datetime as dt
import glob
import hashlib
import io
import json
import os
import re
import sys
import time

TTL_DAYS = 3
MANIFEST = "_TTL.json"
LEDGER_REL = os.path.join(".workbuddy", "archive", "ttl-ledger.md")
ARMED_LINE = "armed: true"

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
# 文档 / 交付物 / 表格，一律 pin
PIN_EXTS = {
    ".md", ".markdown", ".xlsx", ".xls", ".docx", ".doc", ".pdf",
    ".png", ".jpg", ".jpeg", ".gif", ".ofd", ".zip", ".pptx",
    ".csv", ".tsv", ".txt", ".ps1", ".bat", ".sh",
}
# 只有这些扩展名才可能进垃圾白名单
PURGE_EXTS = {".py", ".js", ".pyc", ".json", ".log", ".out", ".tmp", ".html"}
MAX_PURGE_BYTES = 1000000  # 超过 1MB 一律当原件保守处理
QUARANTINE_NAMES = re.compile(r"^(_archive|_drill|_cleared-|publish-|archive)$")
DATE_IN_NAME = re.compile(r"(20\d{2})[-_]?(\d{2})[-_]?(\d{2})")


def emit(text):
    """显式 UTF-8 字节，避开 Windows 管道 cp936。"""
    buf = getattr(sys.stdout, "buffer", None)
    if buf is not None:
        buf.write(text.encode("utf-8"))
        buf.flush()
    else:
        sys.stdout.write(text)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def classify(rel, size):
    """白名单式判定：只有明确匹配才 purgeable，其余一律 pinned。"""
    low = rel.replace("\\", "/").lower()
    for m in PIN_MARKERS:
        if m in low:
            return "pinned", "原件/资产/回滚点:" + m
    ext = os.path.splitext(rel)[1].lower()
    base = os.path.basename(rel).lower()
    # test_*.xlsx 是明确的测试产物，必须排在 .xlsx 通用 pin 之前判定
    if ext == ".xlsx" and base.startswith("test_"):
        return "purgeable", "测试产物"
    if ext in PIN_EXTS:
        return "pinned", "文档/交付物/脚本配置"
    if size > MAX_PURGE_BYTES:
        return "pinned", "大于 1MB，按原件保守处理"
    if ext in PURGE_EXTS:
        return "purgeable", "草稿/诊断/中间产物"
    return "pinned", "不在垃圾白名单"


def archived_at(directory, files):
    """优先用目录名日期，否则用目录内最早文件 mtime。"""
    m = DATE_IN_NAME.search(os.path.basename(directory))
    if m:
        try:
            d = dt.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return d, "dir-name-date"
        except ValueError:
            pass
    times = [os.path.getmtime(f) for f in files if os.path.isfile(f)]
    if times:
        return dt.datetime.fromtimestamp(min(times)), "earliest-file-mtime"
    return dt.datetime.fromtimestamp(os.path.getmtime(directory)), "dir-mtime"


ACTIVE_GUARD_HOURS = 24  # 单元内 24h 内有写入 → 整批延后（体检 v9.3 同款）

# 单元目录本身落在这些位置 → 整目录强制 pin（记忆/日志/回滚点/仓库资产）
AUTO_PIN_DIRS = (
    ".workbuddy\\archive", ".workbuddy/archive", ".workbuddy\\backups",
    ".workbuddy/backups", ".workbuddy\\memory\\archive",
    ".workbuddy/memory/archive", "workbuddy-skills-repo",
)


def build_manifest(directory, ttl_days=TTL_DAYS, force_pin=False):
    low_dir = directory.replace("/", "\\").lower()
    auto_pin = any(m in low_dir for m in AUTO_PIN_DIRS)
    force_pin = bool(force_pin or auto_pin)
    files = [f for f in glob.glob(os.path.join(directory, "**", "*"), recursive=True)
             if os.path.isfile(f) and os.path.basename(f) != MANIFEST]
    when, basis = archived_at(directory, files)
    expires = when + dt.timedelta(days=ttl_days)
    entries = []
    for f in files:
        rel = os.path.relpath(f, directory)
        size = os.path.getsize(f)
        disp, reason = classify(rel, size)
        entries.append({
            "path": rel.replace("\\", "/"),
            "bytes": size,
            "sha256": sha256(f),
            "disposition": "pinned" if force_pin else disp,
            "reason": "强制 pin" if force_pin else reason,
            "deleted_at": None,
        })
    return {
        "version": 1,
        "created_by": "workspace-converge v1.6.0 ttl.py",
        "created_at": dt.datetime.now().isoformat(timespec="seconds"),
        "archived_at": when.isoformat(timespec="seconds"),
        "time_basis": basis,
        "ttl_days": ttl_days,
        "expires_at": expires.isoformat(timespec="seconds"),
        "pinned": bool(force_pin),
        "pin_reason": "整目录强制 pin（记忆/回滚点/仓库资产）" if auto_pin else "",
        "root": directory,
        "files": entries,
    }


def write_manifest(directory, data):
    p = os.path.join(directory, MANIFEST)
    tmp = p + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False, indent=2))
    os.replace(tmp, p)
    return p


def read_manifest(directory):
    p = os.path.join(directory, MANIFEST)
    if not os.path.isfile(p):
        return None
    try:
        return json.load(io.open(p, encoding="utf-8"))
    except Exception:
        return None


def find_quarantines(root):
    """找隔离「单元」：_archive/<日期> 这类内层批次，或 _cleared-<日期> 整体。

    容器目录（_archive / archive）本身不作为单元——否则写在批次目录里的
    manifest 会被漏掉。若容器下没有日期式子目录，才把容器自身当单元。
    """
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d not in (".venv", "node_modules", "__pycache__", ".git")]
        for d in list(dirnames):
            full = os.path.join(dirpath, d)
            # 技能仓库由 git 管，不归收敛技能；写 manifest 会被 sync.sh 带进公开仓库
            if "workbuddy-skills-repo" in full.replace("/", "\\").lower():
                continue
            if not (QUARANTINE_NAMES.match(d) or d.startswith("_cleared-")):
                continue
            try:
                subs = [os.path.join(full, s) for s in os.listdir(full)
                        if os.path.isdir(os.path.join(full, s))]
            except OSError:
                subs = []
            batches = [s for s in subs
                       if DATE_IN_NAME.search(os.path.basename(s))
                       or os.path.basename(s).startswith("memory-")]
            out.extend(batches if batches else [full])
    # 只保留最外层，避免父子重复
    out = sorted(set(out), key=len)
    keep = []
    for p in out:
        if not any(p.startswith(q + os.sep) for q in out if q != p):
            keep.append(p)
    return keep


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


def scan_one(directory, refs, now=None):
    now = now or dt.datetime.now()
    data = read_manifest(directory)
    empty = {"expired": False, "root": directory, "manifest": data or {},
             "purge": [], "ref": [], "pin": [], "notdue": [], "gone": [],
             "deferred": [], "invalid": False}
    # manifest 缺失/损坏/空 → 不删（体检 v9.3 同款）
    if not data or data.get("version") != 1 or not isinstance(data.get("files"), list) \
            or not data["files"]:
        empty["invalid"] = True
        return empty
    try:
        expires = dt.datetime.fromisoformat(data["expires_at"])
    except Exception:
        empty["invalid"] = True
        return empty
    expired = now >= expires
    # 活动守卫：单元内 24h 内有写入 → 整批延后（manifest 自身不算）
    recent = []
    for f in glob.glob(os.path.join(directory, "**", "*"), recursive=True):
        if os.path.isfile(f) and os.path.basename(f) != MANIFEST:
            if (now.timestamp() - os.path.getmtime(f)) < ACTIVE_GUARD_HOURS * 3600:
                recent.append(os.path.relpath(f, directory))
    res = {"expired": expired, "root": directory, "manifest": data,
           "purge": [], "ref": [], "pin": [], "notdue": [], "gone": [],
           "deferred": recent, "invalid": False}
    for e in data["files"]:
        if e.get("deleted_at"):
            continue
        full = os.path.join(directory, e["path"].replace("/", os.sep))
        if not os.path.isfile(full):
            res["gone"].append(e)
            continue
        if data.get("pinned") or e["disposition"] != "purgeable":
            res["pin"].append(e)
            continue
        hit = referenced(e["path"], refs)
        if hit:
            res["ref"].append((e, hit))
            continue
        # 路径断言：规范化后必须落在单元目录内，否则一律保留（防越界）
        if not os.path.abspath(full).startswith(os.path.abspath(directory) + os.sep):
            res["pin"].append(e)
            continue
        if recent:
            continue  # 活动守卫命中 → 整批延后，不进删除清单
        if not expired:
            res["notdue"].append(e)
            continue
        res["purge"].append(e)
    return res


def human(items):
    return "%d 个 / %.1f KB" % (len(items), sum(x["bytes"] for x in items) / 1024.0)


def render(res, title="到期扫描"):
    d = res["manifest"]
    if res.get("invalid"):
        return "[%s] %s\n  manifest 缺失/损坏/空 → 整批不处理\n" % (title, res["root"])
    lines = [
        "[%s] %s" % (title, res["root"]),
        "  归档 %s（依据 %s）｜到期 %s（%d 天）｜%s" % (
            d["archived_at"], d["time_basis"], d["expires_at"], d["ttl_days"],
            "已到期" if res["expired"] else "未到期"),
        "  将删除       %s" % human(res["purge"]),
        "  被引用拦截   %s" % (len(res["ref"]),),
        "  pin 保留     %s" % human(res["pin"]),
        "  未到期       %s" % human(res["notdue"]),
    ]
    if res.get("deferred") and (res["purge"] or res["notdue"]):
        lines.append("  活动守卫延后 %d 个文件（24h 内有写入）" % len(res["deferred"]))
    for e in res["purge"][:8]:
        lines.append("    - 删 %-46s %6.1f KB  %s" % (e["path"], e["bytes"] / 1024.0, e["reason"]))
    if len(res["purge"]) > 8:
        lines.append("    - …… 其余 %d 个" % (len(res["purge"]) - 8))
    for e, hit in res["ref"][:4]:
        lines.append("    ! 引用命中 %-40s ← %s" % (e["path"], hit))
    return "\n".join(lines)


def ledger_path(space_root):
    return os.path.join(space_root, LEDGER_REL)


def is_armed(space_root):
    p = ledger_path(space_root)
    if not os.path.isfile(p):
        return False
    try:
        return ARMED_LINE in io.open(p, encoding="utf-8").read()
    except Exception:
        return False


def arm(space_root):
    p = ledger_path(space_root)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    if not os.path.isfile(p):
        with io.open(p, "w", encoding="utf-8") as f:
            f.write("# TTL 删除台账\n\n%s\n\n首次启用已 dry-run；下次运行收敛起自动 purge 已到期且无引用的垃圾类文件。\n\n" % ARMED_LINE)
            f.write("| 时间 | 隔离目录 | 文件 | 字节 | sha256(前12) | 归档时间 | 理由 |\n")
            f.write("|---|---|---|---|---|---|---|\n")
        return p
    if not is_armed(space_root):
        with io.open(p, "a", encoding="utf-8") as f:
            f.write("\n%s\n" % ARMED_LINE)
    return p


def append_ledger(space_root, directory, entries, archived_at_str):
    p = arm(space_root)
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = []
    for e in entries:
        rows.append("| %s | %s | %s | %d | %s | %s | %s |\n" % (
            stamp, os.path.basename(directory), e["path"], e["bytes"],
            e["sha256"][:12], archived_at_str, e["reason"]))
    with io.open(p, "a", encoding="utf-8") as f:
        f.writelines(rows)
    return p


def purge_one(space_root, res, dry, plan_path):
    """先冻结清单再按清单删（体检 v9.3 同款）；删前重取 size/mtime 复核。"""
    root = res["root"]
    data = res["manifest"]
    removed, blocked, skipped = [], [], []
    plan = []
    for e in res["purge"]:
        full = os.path.join(root, e["path"].replace("/", os.sep))
        if not os.path.isfile(full):
            continue
        st = os.stat(full)
        plan.append({"path": os.path.abspath(full), "rel": e["path"], "size": st.st_size,
                     "mtime": st.st_mtime, "sha256": e["sha256"]})
    if plan and not dry:
        os.makedirs(os.path.dirname(plan_path), exist_ok=True)
        with io.open(plan_path, "a", encoding="utf-8") as f:
            for item in plan:
                f.write(json.dumps({"unit": root, **item}, ensure_ascii=False) + "\n")
    for item, e in zip(plan, res["purge"]):
        if dry:
            removed.append(e)
            continue
        p = item["path"]
        # 路径断言 + 存在性 + 未改动，三重复核
        if not os.path.abspath(p).startswith(os.path.abspath(root) + os.sep) or not os.path.isfile(p):
            skipped.append((e, "路径断言/文件不存在"))
            continue
        st = os.stat(p)
        if st.st_size != item["size"] or abs(st.st_mtime - item["mtime"]) > 1:
            skipped.append((e, "扫描后被改动"))
            continue
        try:
            os.remove(p)
            e["deleted_at"] = dt.datetime.now().isoformat(timespec="seconds")
            removed.append(e)
        except Exception as ex:
            blocked.append((e, str(ex)))
    if removed and not dry:
        write_manifest(root, data)
        append_ledger(space_root, root, removed, data["archived_at"])
        for dirpath, dirnames, filenames in os.walk(root, topdown=False):
            if dirpath == root:
                continue
            try:
                if not os.listdir(dirpath):
                    os.rmdir(dirpath)
            except Exception:
                pass
    remain = sum(1 for f in glob.glob(os.path.join(root, "**", "*"), recursive=True)
                 if os.path.isfile(f) and os.path.basename(f) != MANIFEST)
    return removed, blocked, skipped, remain


def cmd_init(a):
    d = os.path.abspath(a.dir)
    if not os.path.isdir(d):
        emit("目录不存在: %s\n" % d)
        return 2
    if read_manifest(d) and not a.force:
        emit("已有 _TTL.json，未改动（要重建加 --force）\n")
        return 0
    data = build_manifest(d, a.ttl_days, a.pin)
    write_manifest(d, data)
    emit("已建 manifest: %s\n到期 %s｜垃圾类 %d｜pin %d\n" % (
        os.path.join(d, MANIFEST), data["expires_at"],
        sum(1 for x in data["files"] if x["disposition"] == "purgeable"),
        sum(1 for x in data["files"] if x["disposition"] == "pinned")))
    return 0


def cmd_backfill(a):
    roots = a.roots or [r"E:\WorkBuddy"]
    total = 0
    for root in roots:
        for d in find_quarantines(root):
            if read_manifest(d):
                continue
            data = build_manifest(d, a.ttl_days)
            if a.dry_run:
                emit("将补 manifest: %s（%d 文件，到期 %s）\n" % (
                    d, len(data["files"]), data["expires_at"]))
            else:
                write_manifest(d, data)
                emit("已补 manifest: %s（%d 文件，到期 %s）\n" % (
                    d, len(data["files"]), data["expires_at"]))
            total += 1
    emit("合计 %d 个隔离目录\n" % total)
    return 0


def cmd_scan(a):
    space = os.path.abspath(a.space)
    refs = collect_refs(a.refs or [])
    tot = {"purge": 0, "ref": 0, "pin": 0, "notdue": 0}
    found = 0
    for d in find_quarantines(space):
        res = scan_one(d, refs)
        if not res:
            continue
        found += 1
        emit(render(res) + "\n")
        for k in tot:
            tot[k] += len(res[k])
    emit("\n合计 %d 个隔离目录｜将删除 %d｜引用拦截 %d｜pin 保留 %d｜未到期 %d\n" % (
        found, tot["purge"], tot["ref"], tot["pin"], tot["notdue"]))
    if not a.refs:
        emit("注意：未提供 --refs（自动化 prompt 导出），引用检查只覆盖各空间 MEMORY.md 与日志\n")
    return 0


def cmd_purge(a):
    space = os.path.abspath(a.space)
    refs = collect_refs(a.refs or [])
    first = not is_armed(space)
    dry = a.dry_run or first
    if first:
        emit("【首次启用】强制 dry-run，本轮不删除任何文件；已写入 armed 标记。\n\n")
        arm(space)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    plan_path = os.path.join(space, ".workbuddy", "archive", "ttl-plan-%s.jsonl" % stamp)
    results = []
    all_removed, all_blocked, all_skipped = [], [], []
    for d in find_quarantines(space):
        res = scan_one(d, refs)
        if not res or not res["purge"]:
            continue
        removed, blocked, skipped, remain = purge_one(space, res, dry, plan_path)
        all_removed.extend(removed)
        all_blocked.extend(blocked)
        all_skipped.extend(skipped)
        results.append((d, len(removed), len(blocked), len(skipped), remain))
    for d, n, b, s, remain in results:
        emit("  %-56s 删 %d 个%s%s｜单元剩余 %d 个文件\n" % (
            d, n, "" if not b else "，失败 %d" % b,
            "" if not s else "，跳过 %d" % s, remain))
    if not dry:
        emit("冻结清单: %s\n" % plan_path)
    emit("\n%s：%d 个文件（%.1f KB）%s\n" % (
        "预览" if dry else "已删除", len(all_removed),
        sum(x["bytes"] for x in all_removed) / 1024.0,
        "" if dry else "，台账 " + ledger_path(space)))
    if not dry and all_removed:
        emit("台账已记录 sha256 与原路径；被 pin / 被引用 / 未到期的文件全部原地保留。\n")
    return 0


def cmd_pin(a):
    d = os.path.abspath(a.dir)
    data = read_manifest(d)
    if not data:
        emit("没有 manifest，先跑 init\n")
        return 2
    if a.file:
        hit = [e for e in data["files"]
               if e["path"].replace("\\", "/") == a.file.replace("\\", "/")]
        if not hit:
            emit("manifest 里找不到该文件: %s\n" % a.file)
            return 2
        for e in hit:
            e["disposition"] = "pinned"
            e["reason"] = "手动 pin（回归样本/原件）"
        write_manifest(d, data)
        emit("已 pin 单个文件: %s\n" % a.file)
        return 0
    data["pinned"] = True
    for e in data["files"]:
        e["disposition"] = "pinned"
        e["reason"] = "手动 pin"
    write_manifest(d, data)
    emit("已 pin（永不自动删）: %s\n" % d)
    return 0


def main():
    ap = argparse.ArgumentParser(description="隔离区到期清理（TTL）")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("init", help="给单个新归档目录写 _TTL.json")
    p.add_argument("dir")
    p.add_argument("--ttl-days", type=int, default=TTL_DAYS)
    p.add_argument("--pin", action="store_true", help="整目录强制 pin")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_init)
    p = sub.add_parser("backfill", help="给存量隔离目录补 _TTL.json（非破坏）")
    p.add_argument("roots", nargs="*")
    p.add_argument("--ttl-days", type=int, default=TTL_DAYS)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_backfill)
    p = sub.add_parser("scan", help="只读扫描：到期清单 / 引用拦截 / pin / 未到期")
    p.add_argument("space", help="空间根目录（只扫这个空间）")
    p.add_argument("--refs", nargs="*", default=[], help="附加引用文本（如自动化 prompt 导出）")
    p.set_defaults(func=cmd_scan)
    p = sub.add_parser("purge", help="删除已到期、无引用、垃圾类的文件并写台账")
    p.add_argument("space", help="空间根目录（只删这个空间）")
    p.add_argument("--refs", nargs="*", default=[])
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_purge)
    p = sub.add_parser("pin", help="把某个隔离目录或单个文件标为永不自动删")
    p.add_argument("dir")
    p.add_argument("--file", help="只 pin 单个文件（manifest 里的相对路径）")
    p.set_defaults(func=cmd_pin)
    a = ap.parse_args()
    if not getattr(a, "func", None):
        ap.print_help()
        return 0
    return a.func(a)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as ex:
        emit("ttl.py 出错: %s: %s\n" % (type(ex).__name__, ex))
        sys.exit(2)
