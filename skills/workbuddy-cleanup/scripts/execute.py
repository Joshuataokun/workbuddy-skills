# -*- coding: utf-8 -*-
"""v9.3 执行阶段：只按冻结清单删/移，绝不重新枚举目录决定删什么。
先做命名文件灾备（2.6/2.7 共同前置，失败则整节中止）。
每条：路径断言 → Test-Path → 重取 size/mtime 与计划比对 → 逐文件删 → exists 复核。
禁止 -Recurse / 禁止管道；空目录用 os.rmdir 按路径长度倒序删。"""
import os, json, time, shutil, hashlib, stat, sqlite3, datetime, re

HERE = os.path.dirname(os.path.abspath(__file__))
WB = os.environ.get("WB_CLEAN_HOME", r"C:\Users\Administrator\.workbuddy")
DB = os.path.join(WB, "workbuddy.db")
EW = os.environ.get("WB_CLEAN_EW", r"E:\WorkBuddy")
TMP = os.path.abspath(os.environ.get("WB_CLEAN_WORKDIR", os.path.join(HERE, "..", ".work")))
RUNS = os.path.join(WB, "cleanup-runs")
NAMES = os.path.join(WB, "workspace-display-names.json")
QR_E = r"E:\WorkBuddy\.trash-quarantine"
QR_C = r"C:\Users\Administrator\.cleanup-quarantine"
MB = 1024.0 * 1024.0

def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()

def norm(p):
    return os.path.normcase(os.path.normpath(p))

def under(p, root):
    np, nr = norm(p), norm(root)
    return np == nr or np.startswith(nr + os.sep)

def dir_stat(path):
    tb = tf = 0; mx = 0
    if not os.path.isdir(path): return (tb, tf, mx)
    stack = [path]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    if e.is_dir(follow_symlinks=False): stack.append(e.path)
                    else:
                        try:
                            st = e.stat(follow_symlinks=False)
                            tb += st.st_size; tf += 1
                            mx = max(mx, int(st.st_mtime * 1000))
                        except OSError: pass
        except OSError: pass
    return (tb, tf, mx)

def free_bytes(d):
    try: return shutil.disk_usage(d + ":\\").free
    except Exception: return None

def recycle_stat(d):
    tot = cnt = 0
    p = d + ":\\$Recycle.Bin"
    try:
        for root, dirs, fs in os.walk(p):
            for fn in fs:
                try: tot += os.stat(os.path.join(root, fn)).st_size; cnt += 1
                except OSError: pass
    except OSError: pass
    return (tot, cnt)

def disk_snapshot():
    return {"C_free": free_bytes("C"), "E_free": free_bytes("E"),
            "recycle_C": recycle_stat("C")[0], "recycle_C_files": recycle_stat("C")[1],
            "recycle_E": recycle_stat("E")[0], "recycle_E_files": recycle_stat("E")[1]}

def rm_file(path):
    """逐文件删；safe-delete 抛错但已消失也算成功。返回 (ok, err)"""
    if not os.path.exists(path): return (True, "not_found")
    try:
        os.remove(path)
    except Exception:
        try:
            os.chmod(path, stat.S_IWRITE)
            os.remove(path)
        except Exception as e2:
            if not os.path.exists(path): return (True, "")
            return (False, str(e2)[:120])
    if os.path.exists(path): return (False, "still_exists")
    return (True, "")

def rm_empty_dirs(dirs, protect=()):
    """按路径长度倒序删空目录；protect 里的绝不删"""
    pro = set(norm(x) for x in protect)
    removed = []
    for d in sorted(set(dirs), key=lambda x: -len(x)):
        if norm(d) in pro: continue
        if not os.path.isdir(d): continue
        try:
            os.rmdir(d); removed.append(d)
        except OSError:
            pass
    return removed

def verify_item(it):
    """返回 'ok' / 'not_found' / 'changed' / 'refused'"""
    p = it["path"]
    if not os.path.lexists(p): return "not_found"
    try:
        st = os.stat(p)
    except OSError:
        return "not_found"
    if st.st_size != it["size"]: return "changed"
    m = int(st.st_mtime * 1000)
    if abs(m - it["mtime"]) > 2000: return "changed"
    return "ok"

# ---------- 允许根（路径断言） ----------
WL_ROOTS = {
    "logs": os.path.join(WB, "logs"),
    "traces": os.path.join(WB, "traces"),
    "shellSnapshots": os.path.join(WB, "shell-snapshots"),
    "productSpill": os.path.join(WB, "cache", "conversation-product-spill"),
    "clipboardImages": os.path.join(WB, "clipboard-images"),
    "auditLog": os.path.join(WB, "audit-log"),
    "Crash-Log": os.path.join(WB, "logs", "Crash-Log"),
    "topTemp": WB,
}
RET_SESSION_ROOT = os.path.join(WB, "workspace", "sessions")
RET_SESSION_SCOPES = ("modify_backup", "snapfile", ".modify_backup_meta")
RET_BACKUP_ROOT = os.path.join(WB, "backups")
RET_INDEX_ROOTS = [os.path.join(WB, r) for r in
                   ("file-tree-manifests", "file-history", "changes-detail", "changes-index", "artifact-index")]

def cache_assert(it):
    r = it["rule"]
    root = WL_ROOTS.get(r)
    if root is None: return False
    if r == "topTemp":
        # 必须是 WB 顶层文件，且名字匹配
        if os.path.dirname(norm(it["path"])) != norm(WB): return False
        fn = os.path.basename(it["path"])
        return bool(re.match(r"failover\.json\..*\.tmp$", fn) or fn.endswith(".part"))
    return under(it["path"], root)

def ret_assert(e):
    c = e["class"]
    for it in e["items"]:
        p = it["path"]
        if c == "sessionRollback":
            if not under(p, RET_SESSION_ROOT): return False
            rel = norm(p)[len(norm(RET_SESSION_ROOT)) + 1:]
            parts = rel.split(os.sep)
            if len(parts) < 3 or parts[1] not in RET_SESSION_SCOPES: return False
        elif c == "backupSnapshots":
            if not under(p, RET_BACKUP_ROOT): return False
        elif c == "editHistoryIndexes":
            if not any(under(p, r) for r in RET_INDEX_ROOTS): return False
        else:
            return False
    return True

def main():
    with open(os.path.join(TMP, "scan.json"), "r", encoding="utf-8") as f:
        s = json.load(f)
    with open(os.path.join(WB, "cleanup-policy.json"), "r", encoding="utf-8") as f:
        POL = json.load(f)
    ret_enabled = bool(POL.get("retention", {}).get("enabled"))
    sq_enabled = bool(POL.get("spaceQuarantine", {}).get("enabled"))
    ts = s["ts"]
    done = os.path.join(TMP, "exec-%s.done" % ts)
    result_path = os.path.join(TMP, "result.json")
    if os.path.exists(done) and os.path.exists(result_path):
        print("ALREADY_DONE ts=%s (idempotent skip)" % ts)
        return
    t0 = time.time()
    result = {"ts": ts, "now_ms": s["now_ms"], "errors": []}

    # ========== 命名文件灾备（2.6 + 2.7 共同前置） ==========
    nb = {"ok": False, "src_sha": None, "snap_sha": None, "snap_path": None}
    snapdir = os.path.join(RUNS, "names-snapshot")
    snappath = os.path.join(snapdir, "workspace-display-names.json")
    try:
        os.makedirs(snapdir, exist_ok=True)
        src_sha = sha256_file(NAMES)
        shutil.copyfile(NAMES, snappath)  # 字节级复制
        snap_sha = sha256_file(snappath)
        nb = {"ok": src_sha == snap_sha, "src_sha": src_sha, "snap_sha": snap_sha,
              "snap_path": snappath, "match": src_sha == snap_sha}
        if not nb["ok"]:
            result["errors"].append("命名文件灾备 SHA256 不一致，2.6/2.7 整节中止")
    except Exception as e:
        result["errors"].append("命名文件灾备失败：%s；2.6/2.7 整节中止" % str(e)[:150])
    result["names_backup"] = nb

    disk_before = disk_snapshot()
    result["disk_before"] = disk_before

    # ========== 第一类：缓存白名单 ==========
    with open(s["plan_paths"]["cache"], "r", encoding="utf-8") as f:
        cache_plan = json.load(f)
    cache = {"by_rule": {}, "deleted_files": 0, "deleted_bytes": 0,
             "refused": [], "skipped_changed": [], "not_found": 0, "failed": [], "residual": []}
    # 删前基线（执行前实测每个白名单目录）
    before_cache = {}
    for r, root in WL_ROOTS.items():
        if r == "topTemp": continue
        b, f, m = dir_stat(root); before_cache[r] = {"bytes": b, "files": f}
    for it in cache_plan:
        r = it["rule"]
        d = cache["by_rule"].setdefault(r, {"planned": 0, "planned_bytes": 0, "deleted": 0,
                                            "deleted_bytes": 0, "changed": 0, "refused": 0,
                                            "failed": 0, "not_found": 0})
        d["planned"] += 1; d["planned_bytes"] += it["size"]
        if not cache_assert(it):
            d["refused"] += 1; cache["refused"].append(it["path"]); continue
        v = verify_item(it)
        if v == "not_found":
            d["not_found"] += 1; cache["not_found"] += 1; continue
        if v == "changed":
            d["changed"] += 1; cache["skipped_changed"].append(it["path"]); continue
        ok, err = rm_file(it["path"])
        if ok:
            d["deleted"] += 1; d["deleted_bytes"] += it["size"]
            cache["deleted_files"] += 1; cache["deleted_bytes"] += it["size"]
        else:
            d["failed"] += 1; cache["failed"].append({"path": it["path"], "err": err})
    # 删后回读
    for r, root in WL_ROOTS.items():
        if r == "topTemp": continue
        b, f, m = dir_stat(root)
        d = cache["by_rule"].setdefault(r, {"planned": 0, "planned_bytes": 0, "deleted": 0,
                                            "deleted_bytes": 0, "changed": 0, "refused": 0,
                                            "failed": 0, "not_found": 0})
        d["before_bytes"] = before_cache[r]["bytes"]; d["before_files"] = before_cache[r]["files"]
        d["after_bytes"] = b; d["after_files"] = f
        d["freed_bytes"] = before_cache[r]["bytes"] - b
        d["effective"] = d["freed_bytes"] > 0
    result["cache"] = cache
    result["crash_log"] = s["crash_log"]

    # ========== 第二类：隔离区到期释放（2.5） ==========
    with open(s["plan_paths"]["release"], "r", encoding="utf-8") as f:
        release_plan = json.load(f)
    qbefore = {}
    for root in (QR_E, QR_C):
        b, f, m = dir_stat(root); qbefore[root] = {"bytes": b, "files": f}
    rel = {"batches": [], "released_bytes": 0, "deleted_files": 0,
           "interrupted": [], "failed": [], "skipped_changed": [], "refused": [], "not_found": 0}
    for batch in release_plan:
        bp = batch["batchPath"]; root = batch["root"]
        e = {"batch": batch["batch"], "root": root, "planned_files": batch["files"],
             "planned_bytes": batch["bytes"], "ageHours": batch["ageHours"],
             "manifestOk": batch["manifestOk"], "manifestPath": batch["manifestPath"],
             "deleted": 0, "deleted_bytes": 0, "changed": 0, "refused": 0,
             "failed": 0, "not_found": 0, "after_exists": None, "interrupted": False}
        # 路径断言：批次必须直属隔离根且匹配 8 位日期
        if not (under(bp, root) and os.path.dirname(norm(bp)) == norm(root)
                and re.fullmatch(r"\d{8}", os.path.basename(bp))):
            e["refused"] = 1; rel["refused"].append(bp); rel["batches"].append(e); continue
        manifest = batch["manifestPath"]
        items = [x for x in batch["items"] if not x["is_manifest"]]
        manitems = [x for x in batch["items"] if x["is_manifest"]]
        stop = False
        for i, it in enumerate(items):
            if not under(it["path"], bp):
                e["refused"] += 1; rel["refused"].append(it["path"]); continue
            # 中途 manifest 丢失 → 立即停手
            if manifest and (i % 10 == 0) and not os.path.exists(manifest):
                e["interrupted"] = True; stop = True
                rel["interrupted"].append({"batch": batch["batch"], "reason": "manifest 已消失"})
                break
            v = verify_item(it)
            if v == "not_found":
                e["not_found"] += 1; rel["not_found"] += 1; continue
            if v == "changed":
                e["changed"] += 1; rel["skipped_changed"].append(it["path"]); continue
            ok, err = rm_file(it["path"])
            if ok:
                e["deleted"] += 1; e["deleted_bytes"] += it["size"]
            else:
                e["failed"] += 1; rel["failed"].append({"path": it["path"], "err": err})
        if not stop:
            # 最后删 manifest.json
            for it in manitems:
                if not under(it["path"], bp):
                    e["refused"] += 1; rel["refused"].append(it["path"]); continue
                v = verify_item(it)
                if v == "ok":
                    ok, err = rm_file(it["path"])
                    if ok: e["deleted"] += 1; e["deleted_bytes"] += it["size"]
                    else: e["failed"] += 1; rel["failed"].append({"path": it["path"], "err": err})
                elif v == "changed":
                    e["changed"] += 1; rel["skipped_changed"].append(it["path"])
                else:
                    e["not_found"] += 1; rel["not_found"] += 1
            # 子目录按路径长度倒序删空目录，最后删批次根（不删隔离根）
            rm_empty_dirs(batch["dirs"] + [bp], protect=[root, QR_E, QR_C])
        e["after_exists"] = os.path.isdir(bp)
        rel["deleted_files"] += e["deleted"]; rel["released_bytes"] += e["deleted_bytes"]
        rel["batches"].append(e)
    qafter = {}
    for root in (QR_E, QR_C):
        b, f, m = dir_stat(root); qafter[root] = {"bytes": b, "files": f}
    rel["roots_before"] = qbefore; rel["roots_after"] = qafter
    result["release"] = rel

    # ========== 第三类：到期回滚/备份（2.6） ==========
    with open(s["plan_paths"]["retention"], "r", encoding="utf-8") as f:
        retention_plan = json.load(f)
    rbefore = {
        "sessions": dir_stat(RET_SESSION_ROOT)[0],
        "backups": dir_stat(RET_BACKUP_ROOT)[0],
        "indexes": sum(dir_stat(r)[0] for r in RET_INDEX_ROOTS),
    }
    # 会话正文 sid 集合（保护 4 重算）
    jsonl_sids = set()
    pdir = os.path.join(WB, "projects")
    for dn in os.listdir(pdir):
        dp = os.path.join(pdir, dn)
        if os.path.isdir(dp):
            for fn in os.listdir(dp):
                if fn.endswith(".jsonl"): jsonl_sids.add(fn[:-6])
    rt = {"by_class": {}, "deleted_files": 0, "deleted_bytes": 0,
          "refused": [], "skipped_changed": [], "failed": [], "not_found": 0,
          "entries": 0, "skipped_no_jsonl": [], "enabled": False}
    if nb["ok"] and ret_enabled:
        rt["enabled"] = True
        for e in retention_plan:
            c = e["class"]
            d = rt["by_class"].setdefault(c, {"entries": 0, "planned": 0, "planned_bytes": 0,
                                              "deleted": 0, "deleted_bytes": 0, "changed": 0,
                                              "refused": 0, "failed": 0, "not_found": 0})
            if not ret_assert(e):
                d["refused"] += len(e["items"]); rt["refused"].append(e["entry"]); continue
            if c == "sessionRollback":
                sid = e.get("entry")
                # entry 是 sid8；从 items 里取真实 sid
                real_sid = None
                for it in e["items"]:
                    p = it["path"]
                    relp = norm(p)[len(norm(RET_SESSION_ROOT)) + 1:]
                    real_sid = relp.split(os.sep)[0]; break
                if real_sid and real_sid not in jsonl_sids:
                    rt["skipped_no_jsonl"].append(sid)
                    continue
            d["entries"] += 1; rt["entries"] += 1
            for it in e["items"]:
                d["planned"] += 1; d["planned_bytes"] += it["size"]
                v = verify_item(it)
                if v == "not_found":
                    d["not_found"] += 1; rt["not_found"] += 1; continue
                if v == "changed":
                    d["changed"] += 1; rt["skipped_changed"].append(it["path"]); continue
                ok, err = rm_file(it["path"])
                if ok:
                    d["deleted"] += 1; d["deleted_bytes"] += it["size"]
                    rt["deleted_files"] += 1; rt["deleted_bytes"] += it["size"]
                else:
                    d["failed"] += 1; rt["failed"].append({"path": it["path"], "err": err})
        # 删空的具名子目录（保留会话根、具名根、索引根、backups 根）
        all_parents = set()
        for e in retention_plan:
            for it in e["items"]:
                all_parents.add(os.path.dirname(it["path"]))
        protect = [RET_SESSION_ROOT, RET_BACKUP_ROOT, WB, EW] + RET_INDEX_ROOTS
        # 会话根目录 <sid> 本身绝不删
        for e in retention_plan:
            if e["class"] == "sessionRollback":
                for it in e["items"]:
                    relp = norm(it["path"])[len(norm(RET_SESSION_ROOT)) + 1:]
                    parts = relp.split(os.sep)
                    if len(parts) >= 1:
                        protect.append(os.path.join(RET_SESSION_ROOT, parts[0]))
        rt["dirs_removed"] = len(rm_empty_dirs(list(all_parents), protect=protect))
    rafter = {
        "sessions": dir_stat(RET_SESSION_ROOT)[0],
        "backups": dir_stat(RET_BACKUP_ROOT)[0],
        "indexes": sum(dir_stat(r)[0] for r in RET_INDEX_ROOTS),
    }
    rt["before"] = rbefore; rt["after"] = rafter
    rt["diff"] = {k: rbefore[k] - rafter[k] for k in rbefore}
    result["retention"] = rt

    # ========== 第四类：已删空间隔离（2.7） ==========
    with open(s["plan_paths"]["spaces"], "r", encoding="utf-8") as f:
        spaces_plan = json.load(f)
    sp = {"enabled": False, "candidates": len(spaces_plan), "moved": [], "failed": [],
          "skipped_changed": [], "refused": [], "moved_bytes": 0,
          "batch": None, "manifest": None, "rebuilt_shells": [], "items": []}
    if nb["ok"] and sq_enabled:
        sp["enabled"] = True
        day = datetime.datetime.fromtimestamp(time.time()).strftime("%Y%m%d")
        batchdir = os.path.join(QR_E, day)
        # 隔离根必须存在
        if not os.path.isdir(QR_E):
            result["errors"].append("E 盘隔离根不存在，2.7 中止")
            sp["enabled"] = False
        else:
            os.makedirs(batchdir, exist_ok=True)
            sp["batch"] = day
            ok_items = []
            for c in spaces_plan:
                src = c["path"]
                # 路径断言：E:\WorkBuddy 直属一级
                if not (under(src, EW) and os.path.dirname(norm(src)) == norm(EW)):
                    sp["refused"].append(src); continue
                if not os.path.isdir(src):
                    sp["skipped_changed"].append(src); continue
                # 移动前重取体积与最后写入时间，与清单不一致 → 跳过
                b, f, mx = dir_stat(src)
                if b != c["bytes"] or f != c["files"] or (c["lastWrite"] and abs(mx - c["lastWrite"]) > 2000):
                    sp["skipped_changed"].append(src); continue
                dst = os.path.join(batchdir, c["dir"])
                if os.path.exists(dst):
                    sp["failed"].append({"src": src, "err": "目标已存在"}); break
                try:
                    os.rename(src, dst)  # 同盘元数据改名
                except Exception as ex:
                    try:
                        shutil.move(src, dst)
                    except Exception as ex2:
                        sp["failed"].append({"src": src, "err": str(ex2)[:150]}); break
                # 成功判据只看目标存在；源是否被应用重建留到最后单独报告，不算失败、不二次移动
                if not os.path.isdir(dst):
                    sp["failed"].append({"src": src, "err": "目标回读失败"}); break
                sp["moved"].append({"dir": c["dir"], "from": src, "to": dst, "bytes": b, "files": f})
                sp["moved_bytes"] += b
                ok_items.append({"from": src, "to": dst, "size": b, "files": f,
                                 "sha256": "DIR"})
            # 写 manifest（items 非空，格式同第 6 节）
            if ok_items:
                man = {"batch": "%s-%s" % (day, ts.split("-")[1]),
                       "createdAt": int(time.time() * 1000),
                       "reason": "v9.4 方案 C：已删除空间隔离（含文件，同步删DB行）",
                       "items": ok_items}
                mp = os.path.join(batchdir, "manifest.json")
                with open(mp, "w", encoding="utf-8") as f:
                    json.dump(man, f, ensure_ascii=False, indent=1)
                sp["manifest"] = mp; sp["items"] = ok_items
            # 应用重建检查：回读一级目录，重建空壳不二次移动
            for m in sp["moved"]:
                if os.path.isdir(m["from"]):
                    bb, ff, _ = dir_stat(m["from"])
                    sp["rebuilt_shells"].append({"dir": m["dir"], "files": ff, "bytes": bb})
    result["spaces"] = sp

    # ========== 执行后磁盘/回收站 ==========
    time.sleep(1)
    result["disk_after"] = disk_snapshot()
    result["duration_sec"] = round(time.time() - t0, 1)

    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    with open(done, "w", encoding="utf-8") as f:
        f.write("done")
    # 控制台 ASCII 摘要
    print("EXEC_OK ts=%s dur=%ss" % (ts, result["duration_sec"]))
    print("  names_backup=%s match=%s" % (nb["ok"], nb.get("match")))
    print("  cache deleted=%d bytes=%d refused=%d changed=%d failed=%d notfound=%d" % (
        cache["deleted_files"], cache["deleted_bytes"], len(cache["refused"]),
        len(cache["skipped_changed"]), len(cache["failed"]), cache["not_found"]))
    for b in rel["batches"]:
        print("  release batch=%s deleted=%d bytes=%d after_exists=%s interrupted=%s" % (
            b["batch"], b["deleted"], b["deleted_bytes"], b["after_exists"], b["interrupted"]))
    print("  retention enabled=%s entries=%d deleted=%d bytes=%d refused=%d changed=%d" % (
        rt["enabled"], rt["entries"], rt["deleted_files"], rt["deleted_bytes"],
        len(rt["refused"]), len(rt["skipped_changed"])))
    print("  spaces enabled=%s candidates=%d moved=%d bytes=%d rebuilt=%d manifest=%s" % (
        sp["enabled"], sp["candidates"], len(sp["moved"]), sp["moved_bytes"],
        len(sp["rebuilt_shells"]), bool(sp["manifest"])))
    print("  disk C_free %s -> %s ; E_free %s -> %s" % (
        result["disk_before"]["C_free"], result["disk_after"]["C_free"],
        result["disk_before"]["E_free"], result["disk_after"]["E_free"]))
    print("  recycle_C %s -> %s ; recycle_E %s -> %s" % (
        result["disk_before"]["recycle_C"], result["disk_after"]["recycle_C"],
        result["disk_before"]["recycle_E"], result["disk_after"]["recycle_E"]))
    if result["errors"]: print("  ERRORS:", result["errors"])

if __name__ == "__main__":
    main()
