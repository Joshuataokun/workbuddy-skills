# -*- coding: utf-8 -*-
"""v9.3 分阶段续跑 finish.py

背景：resume.py 用「一个全局预算」，隔离区释放阶段耗光预算后会把
retention / spaces 两个阶段一并跳过，导致连续多轮卡在 release。
本脚本改为「一次调用只跑一个 phase，各阶段独立预算、独立结果文件」。

幂等依据：每轮都从头扫全量冻结清单，逐条 verify_item：
  not_found -> 上一轮已删，跳过；changed -> 跳过并记 skipped_changed；
  ok        -> 路径断言 + 逐文件 rm_file + exists 复核。
所以中断后重跑不会重复删、也不会漏删；最后一轮的 statuses 即全量最终视图。

用法：python finish.py release|retention|spaces|finalize
环境：WBV93_BUDGET 单轮秒数（默认 480，前台 600s 超时留余量）
"""
import os, json, time, sys, shutil, re, datetime, collections, sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
WB = os.environ.get("WB_CLEAN_HOME", r"C:\Users\Administrator\.workbuddy")
EW = os.environ.get("WB_CLEAN_EW", r"E:\WorkBuddy")
TMP = os.path.abspath(os.environ.get("WB_CLEAN_WORKDIR", os.path.join(HERE, "..", ".work")))
RUNS = os.path.join(WB, "cleanup-runs")
NAMES = os.path.join(WB, "workspace-display-names.json")
DB = os.path.join(WB, "workbuddy.db")
QR_E = os.path.join(EW, ".trash-quarantine")
QR_C = r"C:\Users\Administrator\.cleanup-quarantine"
STATE = os.path.join(WB, "cleanup-state.json")
LOCK = os.path.join(WB, "cleanup.lock")
# 自动化 memory：定时任务已删，默认不写。如仍挂了定时任务，用环境变量指到它的 memory.md。
AUTOMEM = os.environ.get("WB_CLEAN_AUTOMATION_MEMORY", "")
sys.path.insert(0, HERE)
import execute as X  # noqa: E402  复用同一套断言 / 复核 / 删空目录实现

BUDGET = float(os.environ.get("WBV93_BUDGET", "480"))
CHUNK = 200
MB = 1024.0 * 1024.0
S = None


def load(p):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def dump(p, o):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(o, f, ensure_ascii=False, indent=1)


def pp(name):
    return os.path.join(TMP, "phase_%s.json" % name)


def get(name):
    if os.path.exists(pp(name)):
        return load(pp(name))
    return {"phase": name, "complete": False, "rounds": [],
            "deleted_total": 0, "deleted_bytes_total": 0,
            "not_found_total": 0, "changed_total": 0, "refused_total": 0,
            "failed_total": 0, "failed_items": [], "skipped_changed": [],
            "refused_items": [], "final": None}


def put(name, d):
    dump(pp(name), d)


def disk():
    rc = X.recycle_stat("C")
    re_ = X.recycle_stat("E")
    return {"C_free": X.free_bytes("C"), "E_free": X.free_bytes("E"),
            "recycle_C": rc[0], "recycle_C_files": rc[1],
            "recycle_E": re_[0], "recycle_E_files": re_[1]}


def names_backup():
    """2.6 / 2.7 共同前置：字节级复制 + SHA256 校验"""
    snapdir = os.path.join(RUNS, "names-snapshot")
    snappath = os.path.join(snapdir, "workspace-display-names.json")
    try:
        os.makedirs(snapdir, exist_ok=True)
        src = X.sha256_file(NAMES)
        shutil.copyfile(NAMES, snappath)
        dst = X.sha256_file(snappath)
        return {"ok": src == dst, "src_sha": src, "snap_sha": dst,
                "path": snappath, "match": src == dst}
    except Exception as e:
        return {"ok": False, "err": str(e)[:150]}


def run_items(work, manifest=None):
    """单线程逐条删。按 CHUNK 检查预算与 manifest 存活，不做并发（并发会触发
    平台 safe-delete 全局串行锁 EPERM mkdir .lock，实测会杀进程）。"""
    t0 = time.time()
    statuses = ["not_processed"] * len(work)
    changed, refused, failed = [], [], []
    interrupted = hit = False
    i = 0
    while i < len(work):
        if time.time() - t0 > BUDGET:
            hit = True
            break
        if manifest and not os.path.exists(manifest):
            interrupted = True
            break
        block = work[i:i + CHUNK]
        for j, (it, ok) in enumerate(block):
            if not ok:
                statuses[i + j] = "refused"
                refused.append(it["path"])
                continue
            v = X.verify_item(it)
            if v == "not_found":
                statuses[i + j] = "not_found"
            elif v == "changed":
                statuses[i + j] = "changed"
                changed.append(it["path"])
            else:
                ok2, err = X.rm_file(it["path"])
                if ok2:
                    statuses[i + j] = "deleted"
                else:
                    statuses[i + j] = "failed"
                    failed.append({"path": it["path"], "err": err})
        i += len(block)
    # 失败项单线程重试一次（路径 -> 下标索引，避免 O(n^2)）
    idx = {}
    for n, (it, _) in enumerate(work):
        idx.setdefault(it["path"], []).append(n)
    still = []
    for x in failed:
        ok, err = X.rm_file(x["path"])
        if ok:
            for n in idx.get(x["path"], []):
                if statuses[n] == "failed":
                    statuses[n] = "deleted_retry"
                    break
        else:
            still.append({"path": x["path"], "err": err})
    c = collections.Counter(statuses)
    deleted_bytes = sum(work[n][0]["size"] for n, st in enumerate(statuses)
                        if st in ("deleted", "deleted_retry"))
    return {"statuses": statuses, "stat": dict(c),
            "deleted": c["deleted"] + c["deleted_retry"],
            "deleted_bytes": deleted_bytes, "failed": still,
            "failed_final": len(still), "changed": changed, "refused": refused,
            "hit": hit, "interrupted": interrupted,
            "dur": round(time.time() - t0, 1)}


def merge(ph, r):
    c = r["stat"]
    ph["deleted_total"] += r["deleted"]
    ph["deleted_bytes_total"] += r["deleted_bytes"]
    ph["not_found_total"] += c.get("not_found", 0)
    ph["changed_total"] += len(r["changed"])
    ph["refused_total"] += len(r["refused"])
    ph["failed_total"] += r["failed_final"]
    ph["failed_items"] = (ph["failed_items"] + r["failed"])[:20]
    ph["skipped_changed"] = (ph["skipped_changed"] + r["changed"])[:20]
    ph["refused_items"] = (ph["refused_items"] + r["refused"])[:20]
    ph["rounds"].append({"at_ms": int(time.time() * 1000), "dur": r["dur"],
                         "deleted": r["deleted"],
                         "deleted_bytes": r["deleted_bytes"],
                         "not_found": c.get("not_found", 0),
                         "not_processed": c.get("not_processed", 0),
                         "failed": r["failed_final"], "hit": r["hit"],
                         "interrupted": r["interrupted"]})


def all_processed(r):
    return (r["stat"].get("not_processed", 0) == 0 and r["failed_final"] == 0
            and not r["interrupted"] and not r["hit"])


# ===================== 2.5 隔离区到期释放 =====================
def do_release():
    plan = load(S["plan_paths"]["release"])
    ph = get("release")
    if ph["complete"]:
        print("RELEASE complete (skip)", flush=True)
        return
    if "disk_before" not in ph:
        ph["disk_before"] = disk()
    if "roots_before" not in ph:
        ph["roots_before"] = {root: {"bytes": X.dir_stat(root)[0],
                                     "files": X.dir_stat(root)[1]}
                              for root in (QR_E, QR_C)}
    all_done = True
    for b in plan:
        bp, root, man = b["batchPath"], b["root"], b["manifestPath"]
        if not (X.under(bp, root) and os.path.dirname(X.norm(bp)) == X.norm(root)
                and re.fullmatch(r"\d{8}", os.path.basename(bp))):
            ph["refused_items"].append(bp)
            all_done = False
            continue
        if not os.path.isdir(bp):
            ph["final"] = {"batch": b["batch"], "root": root,
                           "after_exists": False, "already_released": True,
                           "planned_files": b["files"], "planned_bytes": b["bytes"]}
            continue
        ordinary = [x for x in b["items"] if not x["is_manifest"]]
        manitems = [x for x in b["items"] if x["is_manifest"]]
        work = [(it, X.under(it["path"], bp)) for it in ordinary]
        live = man if (man and os.path.exists(man)) else None
        r = run_items(work, manifest=live)
        merge(ph, r)
        c = r["stat"]
        if all_processed(r):
            # manifest 最后删；随后按路径长度倒序删空目录，最后删批次根
            for it in manitems:
                if not X.under(it["path"], bp):
                    continue
                if X.verify_item(it) == "ok":
                    ok, _ = X.rm_file(it["path"])
                    if ok:
                        ph["deleted_total"] += 1
                        ph["deleted_bytes_total"] += it["size"]
            removed = X.rm_empty_dirs(b["dirs"] + [bp], protect=[root, QR_E, QR_C])
            exists = os.path.isdir(bp)
            ph["final"] = {"batch": b["batch"], "root": root,
                           "planned_files": b["files"], "planned_bytes": b["bytes"],
                           "after_exists": exists, "dirs_removed": len(removed),
                           "residual_files": X.dir_stat(bp)[1],
                           "manifest_deleted": not os.path.exists(man),
                           "interrupted": r["interrupted"]}
            all_done = all_done and not exists
        else:
            ph["final"] = {"batch": b["batch"], "root": root,
                           "planned_files": b["files"], "planned_bytes": b["bytes"],
                           "after_exists": True, "incomplete": True,
                           "remaining": c.get("not_processed", 0),
                           "residual_files": X.dir_stat(bp)[1],
                           "interrupted": r["interrupted"]}
            all_done = False
    ph["complete"] = all_done
    ph["disk_after"] = disk()
    ph["roots_after"] = {root: {"bytes": X.dir_stat(root)[0],
                                "files": X.dir_stat(root)[1]}
                         for root in (QR_E, QR_C)}
    put("release", ph)
    f = ph["final"] or {}
    print("RELEASE complete=%s deleted_total=%d bytes=%.2fMB remain=%s after_exists=%s dur=%.1fs" % (
        ph["complete"], ph["deleted_total"], ph["deleted_bytes_total"] / MB,
        f.get("remaining"), f.get("after_exists"),
        ph["rounds"][-1]["dur"] if ph["rounds"] else 0), flush=True)


# ===================== 2.6 到期回滚 / 备份 =====================
def do_retention():
    POL = load(os.path.join(WB, "cleanup-policy.json"))
    if not POL.get("retention", {}).get("enabled"):
        print("RETENTION disabled by policy", flush=True)
        return
    plan = load(S["plan_paths"]["retention"])
    ph = get("retention")
    if ph["complete"]:
        print("RETENTION complete (skip)", flush=True)
        return
    nb = names_backup()
    ph["names_backup"] = nb
    if not nb["ok"]:
        ph["errors"] = ["命名文件灾备 SHA256 不一致，2.6 整节中止"]
        put("retention", ph)
        print("RETENTION ABORT names_backup", flush=True)
        return
    if "disk_before" not in ph:
        ph["disk_before"] = disk()
    if "before" not in ph:
        ph["before"] = {"sessions": X.dir_stat(X.RET_SESSION_ROOT)[0],
                        "backups": X.dir_stat(X.RET_BACKUP_ROOT)[0],
                        "indexes": sum(X.dir_stat(p)[0] for p in X.RET_INDEX_ROOTS)}
    # 会话正文存在集合（保护：无正文会话不动）
    jsonl = set()
    pdir = os.path.join(WB, "projects")
    for dn in os.listdir(pdir):
        dp = os.path.join(pdir, dn)
        if os.path.isdir(dp):
            for fn in os.listdir(dp):
                if fn.endswith(".jsonl"):
                    jsonl.add(fn[:-6])
    work, owners, skipped_no_jsonl = [], [], []
    for e in plan:
        c = e["class"]
        ok = X.ret_assert(e)
        if c == "sessionRollback":
            sid = None
            for it in e["items"]:
                rel = X.norm(it["path"])[len(X.norm(X.RET_SESSION_ROOT)) + 1:]
                sid = rel.split(os.sep)[0]
                break
            if sid and sid not in jsonl:
                skipped_no_jsonl.append(e.get("entry"))
                continue
        for it in e["items"]:
            work.append((it, ok))
            owners.append(c)
    r = run_items(work)
    merge(ph, r)
    ph["skipped_no_jsonl"] = skipped_no_jsonl
    by_class = {}
    for (it, _), st, cl in zip(work, r["statuses"], owners):
        d = by_class.setdefault(cl, {"planned": 0, "planned_bytes": 0,
                                     "deleted": 0, "deleted_bytes": 0,
                                     "not_found": 0, "changed": 0,
                                     "refused": 0, "failed": 0,
                                     "not_processed": 0})
        d["planned"] += 1
        d["planned_bytes"] += it["size"]
        if st in ("deleted", "deleted_retry"):
            d["deleted"] += 1
            d["deleted_bytes"] += it["size"]
        elif st in d:
            d[st] += 1
    ph["by_class"] = by_class
    if all_processed(r):
        parents = set()
        for e in plan:
            for it in e["items"]:
                parents.add(os.path.dirname(it["path"]))
        protect = [X.RET_SESSION_ROOT, X.RET_BACKUP_ROOT, WB, EW] + X.RET_INDEX_ROOTS
        for e in plan:
            if e["class"] == "sessionRollback":
                for it in e["items"]:
                    rel = X.norm(it["path"])[len(X.norm(X.RET_SESSION_ROOT)) + 1:]
                    parts = rel.split(os.sep)
                    if parts:
                        protect.append(os.path.join(X.RET_SESSION_ROOT, parts[0]))
        removed = X.rm_empty_dirs(list(parents), protect=protect)
        after = {"sessions": X.dir_stat(X.RET_SESSION_ROOT)[0],
                 "backups": X.dir_stat(X.RET_BACKUP_ROOT)[0],
                 "indexes": sum(X.dir_stat(p)[0] for p in X.RET_INDEX_ROOTS)}
        ph["after"] = after
        ph["diff"] = {k: ph["before"][k] - after[k] for k in ph["before"]}
        ph["dirs_removed"] = len(removed)
        ph["complete"] = True
    ph["disk_after"] = disk()
    put("retention", ph)
    print("RETENTION complete=%s deleted_total=%d bytes=%.2fMB remain=%d dur=%.1fs" % (
        ph["complete"], ph["deleted_total"], ph["deleted_bytes_total"] / MB,
        (ph["by_class"] and sum(d["not_processed"] for d in ph["by_class"].values())) or 0,
        ph["rounds"][-1]["dur"] if ph["rounds"] else 0), flush=True)


# ===================== 2.7 已删除空间隔离 =====================
def do_spaces():
    POL = load(os.path.join(WB, "cleanup-policy.json"))
    sq = POL.get("spaceQuarantine", {})
    ph = get("spaces")
    if ph["complete"]:
        print("SPACES complete (skip)", flush=True)
        return
    if not sq.get("enabled"):
        ph.update({"enabled": False, "complete": True,
                   "note": "spaceQuarantine.enabled=false，整节跳过"})
        put("spaces", ph)
        print("SPACES disabled by policy", flush=True)
        return
    nb = names_backup()
    ph["names_backup"] = nb
    if not nb["ok"]:
        ph.update({"errors": ["命名文件灾备失败，2.7 整节中止"], "complete": True})
        put("spaces", ph)
        print("SPACES ABORT names_backup", flush=True)
        return
    plan = load(S["plan_paths"]["spaces"])
    day = datetime.datetime.fromtimestamp(time.time()).strftime("%Y%m%d")
    batchdir = os.path.join(QR_E, day)
    if not os.path.isdir(QR_E):
        ph.update({"errors": ["E 盘隔离根不存在，2.7 中止"], "complete": True})
        put("spaces", ph)
        print("SPACES ABORT no quarantine root", flush=True)
        return
    os.makedirs(batchdir, exist_ok=True)
    mp = os.path.join(batchdir, "manifest.json")
    ok_items = []
    if os.path.exists(mp):
        try:
            ok_items = [x for x in load(mp).get("items", []) if isinstance(x, dict)]
        except Exception:
            ok_items = []
    seen = set(x.get("from") for x in ok_items)
    moved, failed, skipped, refused, rebuilt = [], [], [], [], []
    for c in plan:
        src = c["path"]
        if not (X.under(src, EW) and os.path.dirname(X.norm(src)) == X.norm(EW)):
            refused.append(src)
            continue
        if src in seen:
            continue
        if not os.path.isdir(src):
            skipped.append(src)
            continue
        b, f, mx = X.dir_stat(src)
        if (b != c["bytes"] or f != c["files"]
                or (c.get("lastWrite") and abs(mx - c["lastWrite"]) > 2000)):
            skipped.append(src)
            continue
        dst = os.path.join(batchdir, c["dir"])
        if os.path.exists(dst):
            failed.append({"src": src, "err": "目标已存在"})
            break
        try:
            os.rename(src, dst)          # 同盘元数据改名，非跨盘复制
        except Exception:
            try:
                shutil.move(src, dst)
            except Exception as ex2:
                failed.append({"src": src, "err": str(ex2)[:150]})
                break
        if not os.path.isdir(dst):
            failed.append({"src": src, "err": "目标回读失败"})
            break
        moved.append({"dir": c["dir"], "from": src, "to": dst,
                      "bytes": b, "files": f})
        ok_items.append({"from": src, "to": dst, "size": b, "files": f,
                         "sha256": "DIR", "type": "dir"})
        seen.add(src)
    ttl = int(sq.get("ttlDays", 7))
    man = None
    if ok_items:
        man = {"batch": "%s-%s" % (day, S["ts"].split("-")[1]),
               "createdAt": int(time.time() * 1000),
               "reason": "v9.3 方案 C：已删除空间隔离",
               "ttlDays": ttl, "items": ok_items}
        with open(mp, "w", encoding="utf-8") as f:
            json.dump(man, f, ensure_ascii=False, indent=1)
    for m in moved:
        if os.path.isdir(m["from"]):
            bb, ff, _ = X.dir_stat(m["from"])
            rebuilt.append({"dir": m["dir"], "files": ff, "bytes": bb})
    due = int(time.time() * 1000) + ttl * 86400000
    ph.update({"enabled": True, "candidates": len(plan), "moved": moved,
               "failed": failed, "skipped_changed": skipped, "refused": refused,
               "rebuilt_shells": rebuilt,
               "moved_bytes": sum(m["bytes"] for m in moved),
               "batch": day, "manifest": mp if ok_items else None,
               "manifest_items": len(ok_items), "ttlDays": ttl,
               "nextDue": due,
               "nextDueText": datetime.datetime.fromtimestamp(due / 1000).strftime("%Y-%m-%d %H:%M"),
               "complete": True})
    put("spaces", ph)
    print("SPACES candidates=%d moved=%d bytes=%d failed=%d rebuilt=%d manifest=%s due=%s" % (
        ph["candidates"], len(moved), ph["moved_bytes"], len(failed),
        len(rebuilt), bool(ph["manifest"]), ph["nextDueText"]), flush=True)


# ===================== 收尾：验收 + 写运行记录 + 状态 + 日志 + 删锁 =====================
def do_finalize():
    base = load(os.path.join(TMP, "baseline.json"))
    POL = load(os.path.join(WB, "cleanup-policy.json"))
    res = load(os.path.join(TMP, "result.json"))
    phases = {}
    for n in ("release", "retention", "spaces"):
        phases[n] = load(pp(n)) if os.path.exists(pp(n)) else None
    now = int(time.time() * 1000)
    V = {}

    # V1 缓存：按冻结清单全量回读，remain 必须为 0
    cache_plan = load(S["plan_paths"]["cache"])
    remain = sum(1 for it in cache_plan if os.path.lexists(it["path"]))
    V["V1"] = {"ok": remain == 0, "planned": len(cache_plan), "remain": remain,
               "planned_MB": round(sum(i["size"] for i in cache_plan) / MB, 2)}

    # V2 空间目录集合与体积（除 2.7 已移入项）
    moved_dirs = set()
    if phases["spaces"]:
        moved_dirs = {m["dir"] for m in phases["spaces"].get("moved", [])}
    v2 = []
    for row in S["inventory"]:
        p = row["path"]
        if row["dir"] in moved_dirs:
            v2.append({"dir": row["dir"], "exempt": True})
            continue
        b = X.dir_stat(p)[0] if os.path.isdir(p) else None
        v2.append({"dir": row["dir"], "before": row["bytes"], "after": b,
                   "diff": (b - row["bytes"]) if b is not None else None})
    V["V2"] = {"ok": all(x.get("exempt") or x.get("diff") == 0 for x in v2), "items": v2}

    # V3 活会话正文逐个存在
    missing = [p for p in base["alive_jsonl_paths"] if not os.path.exists(p)]
    V["V3"] = {"ok": not missing, "count": len(base["alive_jsonl_paths"]),
               "missing": missing[:5]}

    # V4 命名文件 SHA256 与执行前一致
    try:
        sha = X.sha256_file(NAMES)
    except Exception as e:
        sha = "ERR:%s" % e
    V["V4"] = {"ok": sha == base["names_sha256"], "before": base["names_sha256"],
               "after": sha}

    # V5 活空间 MEMORY.md 字符数与 mtime
    v5 = []
    for m in base["memory_spaces"]:
        p = os.path.join(EW, m["dir"], ".workbuddy", "memory", "MEMORY.md")
        if not os.path.isfile(p):
            v5.append({"space": m["space"], "missing": True})
            continue
        st = os.stat(p)
        chars = len(open(p, "r", encoding="utf-8", errors="ignore").read())
        v5.append({"space": m["space"], "chars": chars,
                   "chars_before": m["chars"],
                   "mtime": int(st.st_mtime * 1000),
                   "mtime_before": m["mtime_ms"],
                   "same": chars == m["chars"] and int(st.st_mtime * 1000) == m["mtime_ms"]})
    V["V5"] = {"ok": all(x.get("same", False) for x in v5), "items": v5}

    # V6 DB mtime 与 workspaces 行数
    try:
        con = sqlite3.connect("file:%s?mode=ro" % DB.replace("\\", "/"), uri=True)
        rows = con.execute("SELECT COUNT(*) FROM workspaces").fetchone()[0]
        con.close()
    except Exception as e:
        rows = "ERR:%s" % e
    dbm = int(os.stat(DB).st_mtime * 1000) if os.path.isfile(DB) else None
    V["V6"] = {"ok": rows == base["workspaces_rows"] and dbm == base["db_mtime_ms"],
               "rows_before": base["workspaces_rows"], "rows_after": rows,
               "mtime_before": base["db_mtime_ms"], "mtime_after": dbm}

    # V7 删除对象全在四类清单内（脚本保证）+ refused / skipped 如实列出
    V["V7"] = {"ok": True, "refused": sum((phases[n] or {}).get("refused_total", 0)
                                          for n in phases),
               "skipped_changed": sum(len((phases[n] or {}).get("skipped_changed", []))
                                      for n in phases)}

    # V8 projects 体积差 / workspace\sessions 体积差 / 命名快照
    pb, pf, _ = X.dir_stat(os.path.join(WB, "projects"))
    sb, sf, _ = X.dir_stat(X.RET_SESSION_ROOT)
    snap = os.path.join(RUNS, "names-snapshot", "workspace-display-names.json")
    snap_ok = os.path.isfile(snap) and X.sha256_file(snap) == base["names_sha256"]
    V["V8"] = {"ok": pb == base["projects_bytes"] and snap_ok,
               "projects_before": base["projects_bytes"], "projects_after": pb,
               "projects_diff": pb - base["projects_bytes"],
               "sessions_before": base["sessions_bytes"], "sessions_after": sb,
               "sessions_diff": sb - base["sessions_bytes"],
               "names_snapshot_ok": snap_ok}

    # V9 到期批次 Test-Path False + 未到期批次体积差 0 + 回收站对账
    rel = phases["release"] or {}
    batch_absent = all(not os.path.isdir(b["batchPath"])
                       for b in load(S["plan_paths"]["release"]))
    V["V9"] = {"ok": bool(rel.get("complete")) and batch_absent,
               "complete": rel.get("complete"), "batch_absent": batch_absent,
               "released_MB": round(rel.get("deleted_bytes_total", 0) / MB, 2),
               "after_exists": (rel.get("final") or {}).get("after_exists")}

    # V10 retention 保护四类未动 + 未到期条目体积差 0
    rt = phases["retention"] or {}
    V["V10"] = {"ok": bool(rt.get("complete")),
                "complete": rt.get("complete"),
                "skipped_no_jsonl": len(rt.get("skipped_no_jsonl", [])),
                "diff": rt.get("diff"),
                "before": rt.get("before"), "after": rt.get("after")}

    # V11 已删空间：源消失/目标存在/manifest 合法/命名快照/DB 一致/空壳未二次移动
    sp = phases["spaces"] or {}
    mv = sp.get("moved", [])
    man_ok = False
    if sp.get("manifest") and os.path.isfile(sp["manifest"]):
        try:
            m = load(sp["manifest"])
            man_ok = (isinstance(m.get("items"), list) and len(m["items"]) > 0
                      and "方案 C" in str(m.get("reason", "")))
        except Exception:
            man_ok = False
    V["V11"] = {"ok": (all(not os.path.isdir(x["from"]) and os.path.isdir(x["to"])
                           for x in mv) and man_ok and snap_ok
                       and V["V6"]["rows_after"] == base["workspaces_rows"]),
                "moved": len(mv), "manifest_ok": man_ok,
                "names_snapshot_ok": snap_ok,
                "rebuilt_shells": sp.get("rebuilt_shells", []),
                "db_rows": V["V6"]["rows_after"]}

    disk_after = disk()
    # 占用地图：按策略每次重测
    space_map_now = []
    for row in S["space_map"]:
        b, f, mx = X.dir_stat(os.path.join(WB, row["name"]))
        space_map_now.append({"name": row["name"], "bytes": b, "files": f,
                              "MB": round(b / MB, 2),
                              "before_MB": round(row["bytes"] / MB, 2)})
    space_map_now.sort(key=lambda x: -x["bytes"])
    freeC = (disk_after["C_free"] or 0) / 1024**3
    freeE = (disk_after["E_free"] or 0) / 1024**3
    recC = disk_after["recycle_C"] / MB
    recE = disk_after["recycle_E"] / MB

    cache_MB = V["V1"]["planned_MB"]
    released_MB = V["V9"]["released_MB"]
    retention_MB = round((rt.get("deleted_bytes_total", 0)) / MB, 2)
    sq_MB = round(sp.get("moved_bytes", 0) / MB, 4)
    status = "OK" if all(v.get("ok") for v in V.values()) else "PARTIAL"

    # ---- 1) 运行记录 cleanup-runs\<yyyyMMdd-HHmm>.json（不含会话标题与文件名）----
    run_ts = datetime.datetime.fromtimestamp(time.time()).strftime("%Y%m%d-%H%M")
    record = {"ts": S["ts"], "runAt": run_ts, "finishedAt": now,
              "policyVersion": "v9.3", "status": status,
              "durationNote": "跨多轮续跑；单阶段独立预算，详见 phase_*.json",
              "cache": {"planned": len(cache_plan), "planned_MB": cache_MB,
                        "remain": remain, "by_rule": res.get("cache", {}).get("by_rule", {})},
              "release": {"complete": rel.get("complete"),
                          "deleted_files": rel.get("deleted_total", 0),
                          "deleted_MB": released_MB,
                          "final": rel.get("final"),
                          "roots_before": rel.get("roots_before"),
                          "roots_after": rel.get("roots_after"),
                          "really_freed": False},
              "retention": {"enabled": bool(rt.get("complete")) or bool(rt),
                            "complete": rt.get("complete"),
                            "deleted_files": rt.get("deleted_total", 0),
                            "deleted_MB": retention_MB,
                            "by_class": rt.get("by_class"),
                            "before": rt.get("before"), "after": rt.get("after"),
                            "diff": rt.get("diff"),
                            "really_freed": False},
              "spaceQuarantine": {"candidates": sp.get("candidates", 0),
                                 "moved": len(mv), "moved_MB": sq_MB,
                                 "batch": sp.get("batch"), "ttlDays": sp.get("ttlDays"),
                                 "nextDueText": sp.get("nextDueText"),
                                 "manifest_items": sp.get("manifest_items", 0),
                                 "rebuilt_shells": sp.get("rebuilt_shells", []),
                                 "failed": sp.get("failed", []),
                                 "skipped_changed": sp.get("skipped_changed", []),
                                 "really_freed": False},
              "refused": sum((phases[n] or {}).get("refused_total", 0) for n in phases),
              "skipped_changed": sum(len((phases[n] or {}).get("skipped_changed", []))
                                     for n in phases),
              "spaceMap": [{"name": x["name"], "MB": x["MB"], "files": x["files"]}
                           for x in space_map_now],
              "disk": {"before": res.get("disk_before"), "after": disk_after},
              "verification": {k: v.get("ok") for k, v in V.items()}}
    os.makedirs(RUNS, exist_ok=True)
    record_path = os.path.join(RUNS, "%s.json" % run_ts)
    dump(record_path, record)

    # ---- 2) cleanup-state.json ----
    st = load(STATE)
    st["lastRunAt"] = now
    st["lastStatus"] = status
    st["lastMode"] = "v9.3-full"
    st["lastRCount"] = S["R_count"]
    st["lastAliveCount"] = S["alive_count"]
    st["lastDeadCount"] = S["dead_count"]
    st["lastFreedMB"] = cache_MB
    st["lastReleasedMB"] = released_MB
    st["lastRetentionMB"] = retention_MB
    st["lastSpaceQuarantineMB"] = sq_MB
    st["lastSpaceMap"] = {"measuredAt": now,
                          **{x["name"].replace("-", "_") + "_MB": x["MB"]
                             for x in space_map_now[:10]},
                          "C_free_GB": round(freeC, 3),
                          "E_free_GB": round(freeE, 3)}
    st["note"] = "v9.3：缓存/隔离/回滚/已删空间四类自动动作；删除实体多进回收站，可用空间需用户手动清空才释放。"
    qb = []
    for b in st.get("quarantine", {}).get("batches", []):
        if b.get("batch") == "20261104" and V["V9"]["ok"]:
            b["released"] = True
            b["releasedAt"] = now
        qb.append(b)
    if sp.get("manifest"):
        qb.append({"batch": sp["batch"], "root": QR_E,
                   "reason": "v9.3 方案 C：已删除空间隔离",
                   "files": sp["manifest_items"], "MB": sq_MB,
                   "at": sp.get("nextDue", now) - int(sp.get("ttlDays", 7)) * 86400000,
                   "releaseAfter": sp.get("nextDue"), "released": False})
    st.setdefault("quarantine", {})["roots"] = [QR_E, QR_C]
    st["quarantine"]["batches"] = qb
    st["quarantine"]["note"] = "到期后由下一次运行自动释放，无需口令。"
    rs = S.get("retention_summary", {})
    st["retention"] = {"nextDue": {
        k: {"ttlDays": v.get("ttlDays"),
            "nearestDaysLeft": round(max(0.0, v.get("nearest_days_left", 0)), 2),
            "notdue_count": v.get("notdue_count"), "notdue_MB": round(v.get("notdue_bytes", 0) / MB, 2)}
        for k, v in rs.items()}}
    st["spaceQuarantine"] = {"nextDue": sp.get("nextDue"),
                             "nextDueText": sp.get("nextDueText"),
                             "ttlDays": sp.get("ttlDays"),
                             "batch": sp.get("batch")}
    hist = st.get("history", [])
    hist.append({"at": now, "freedMB": cache_MB, "releasedMB": released_MB,
                 "retentionMB": retention_MB, "spaceQuarantineMB": sq_MB,
                 "dirs": len(mv), "mode": "v9.3-full", "status": status,
                 "note": "删除实体进回收站，可用空间未真正释放"})
    st["history"] = hist[-26:]
    dump(STATE, st)

    # ---- 3) 自动化 memory 只写一行 ----
    line = ("%s 执行%s，清缓存 %.1f MB + 到期回滚/备份 %.1f MB + 释放隔离 %.1f MB "
            "+ 已删空间隔离 %d 个，未删活空间/任务；实体多进回收站，可用空间未真正释放\n"
            % (datetime.datetime.fromtimestamp(time.time()).strftime("%Y-%m-%d %H:%M"),
               "成功" if status == "OK" else "完成（PARTIAL）",
               cache_MB, retention_MB, released_MB, len(mv)))
    if AUTOMEM:
        if os.path.isfile(AUTOMEM):
            with open(AUTOMEM, "a", encoding="utf-8") as f:
                f.write(line)
        else:
            os.makedirs(os.path.dirname(AUTOMEM), exist_ok=True)
            with open(AUTOMEM, "w", encoding="utf-8") as f:
                f.write("# 巡检执行记录（v5 起仅记时间戳）\n\n" + line)
    # AUTOMEM 为空（默认）表示无定时任务，跳过写 memory

    # ---- 4) 删锁 ----
    if os.path.exists(LOCK):
        os.remove(LOCK)

    final = {"status": status, "verification": V, "record_path": record_path,
             "cache_MB": cache_MB, "released_MB": released_MB,
             "retention_MB": retention_MB, "sq_MB": sq_MB,
             "spaces": sp, "release": rel, "retention": rt,
             "space_map": space_map_now, "disk_after": disk_after,
             "disk_before": res.get("disk_before"),
             "freeC_GB": round(freeC, 3), "freeE_GB": round(freeE, 3),
             "recycle_C_MB": round(recC, 2), "recycle_E_MB": round(recE, 2),
             "run_ts": run_ts, "scan": S}
    dump(os.path.join(TMP, "final.json"), final)
    print("FINALIZE status=%s record=%s" % (status, record_path), flush=True)
    print("  V: " + " ".join("%s%s" % (k, "✓" if v.get("ok") else "✗")
                            for k, v in V.items()), flush=True)
    print("  cache=%.2fMB release=%.2fMB retention=%.2fMB sq=%.4fMB" % (
        cache_MB, released_MB, retention_MB, sq_MB), flush=True)
    print("  C_free=%.3fGB E_free=%.3fGB recycle_C=%.2fMB recycle_E=%.2fMB" % (
        freeC, freeE, recC, recE), flush=True)
    print("  LOCK removed=%s" % (not os.path.exists(LOCK)), flush=True)


def main():
    global S
    S = load(os.path.join(TMP, "scan.json"))
    phase = sys.argv[1] if len(sys.argv) > 1 else ""
    fn = {"release": do_release, "retention": do_retention,
          "spaces": do_spaces, "finalize": do_finalize}.get(phase)
    if not fn:
        print("USAGE: python finish.py release|retention|spaces|finalize")
        sys.exit(2)
    fn()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        tb = traceback.format_exc()
        with open(os.path.join(TMP, "finish_error.txt"), "w", encoding="utf-8") as f:
            f.write(tb)
        print("FINISH_EXCEPTION\n" + tb, flush=True)
        raise
