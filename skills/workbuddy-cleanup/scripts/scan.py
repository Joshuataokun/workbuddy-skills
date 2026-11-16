# -*- coding: utf-8 -*-
"""v9.3 扫描阶段：只读。采集体检数据 + 验收基线 + 冻结四份计划清单。
绝不删除/移动任何对象。所有判定依据 cleanup-policy.json。"""
import sqlite3, os, json, re, time, datetime, hashlib, shutil

# 工作目录：默认技能自带 .work/，可用 WB_CLEAN_WORKDIR 覆盖（例如续跑旧的冻结计划）
HERE = os.path.dirname(os.path.abspath(__file__))
WB = os.environ.get("WB_CLEAN_HOME", r"C:\Users\Administrator\.workbuddy")
DB = os.path.join(WB, "workbuddy.db")
EW = os.environ.get("WB_CLEAN_EW", r"E:\WorkBuddy")
TMP = os.environ.get("WB_CLEAN_WORKDIR", os.path.join(HERE, "..", ".work"))
TMP = os.path.abspath(TMP)
os.makedirs(TMP, exist_ok=True)
RUNS = os.path.join(WB, "cleanup-runs")
POL = os.path.join(WB, "cleanup-policy.json")
STATE = os.path.join(WB, "cleanup-state.json")
NAMES = os.path.join(WB, "workspace-display-names.json")

MB = 1024.0 * 1024.0
GB = 1024.0 * 1024.0 * 1024.0

def now_ms():
    return int(time.time() * 1000)

def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()

def norm(p):
    return os.path.normcase(os.path.normpath(p))

def under(p, root):
    """完整路径规范化后必须以 root + sep 开头"""
    np, nr = norm(p), norm(root)
    return np.startswith(nr + os.sep)

def dir_stat(path, skip_names=()):
    """返回 (bytes, files, max_mtime_ms, empty_dirs)。os.scandir 递归，逐目录有限遍历。"""
    tb = 0; tf = 0; mx = 0; edirs = []
    if not os.path.isdir(path):
        return (0, 0, 0, [])
    stack = [path]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                nchild = 0
                for e in it:
                    nchild += 1
                    if e.is_dir(follow_symlinks=False):
                        if e.name in skip_names:
                            continue
                        stack.append(e.path)
                    else:
                        try:
                            st = e.stat(follow_symlinks=False)
                            tb += st.st_size; tf += 1
                            m = int(st.st_mtime * 1000)
                            if m > mx: mx = m
                        except OSError:
                            pass
                if nchild == 0:
                    edirs.append(d)
        except OSError:
            pass
    return (tb, tf, mx, edirs)

def files_under(path, skip_dir_names=()):
    """yield (fullpath, size, mtime_ms, is_manifest)"""
    if not os.path.isdir(path):
        return
    stack = [path]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    if e.is_dir(follow_symlinks=False):
                        if e.name not in skip_dir_names:
                            stack.append(e.path)
                    else:
                        try:
                            st = e.stat(follow_symlinks=False)
                            yield (e.path, st.st_size, int(st.st_mtime * 1000), e.name == "manifest.json")
                        except OSError:
                            pass
        except OSError:
            pass

def dirs_under(path):
    out = []
    if not os.path.isdir(path):
        return out
    stack = [path]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    if e.is_dir(follow_symlinks=False):
                        out.append(e.path)
                        stack.append(e.path)
        except OSError:
            pass
    return out

def fmt_ms(ms):
    if not ms: return "-"
    return datetime.datetime.fromtimestamp(ms / 1000.0).strftime("%Y-%m-%d %H:%M")

def main():
    NOW = now_ms()
    ts = datetime.datetime.fromtimestamp(NOW / 1000.0).strftime("%Y%m%d-%H%M")
    with open(POL, "r", encoding="utf-8") as f:
        pol = json.load(f)

    active_h = pol.get("guards", {}).get("activeHours", 24)
    active_ms = active_h * 3600 * 1000
    q = pol["quarantine"]
    q_ttl_ms = q.get("ttlDays", 7) * 86400000
    q_guard_ms = q.get("releaseRecentWriteGuardHours", 24) * 3600000
    ret = pol.get("retention", {})
    ret_enabled = bool(ret.get("enabled"))
    sq = pol.get("spaceQuarantine", {})
    sq_enabled = bool(sq.get("enabled"))
    sq_ttl_ms = sq.get("ttlDays", 7) * 86400000
    cr = sq.get("candidateRule", {})
    sq_max_bytes = cr.get("maxDirMB", 1) * MB
    sq_written_ms = cr.get("excludeIfWrittenWithinHours", 24) * 3600000
    sq_exclude = set(cr.get("excludeDirNames", []))

    out = {"ts": ts, "now_ms": NOW, "active_h": active_h,
           "q_ttl_days": q.get("ttlDays", 7), "sq_ttl_days": sq.get("ttlDays", 7)}
    out["policy_retention_days"] = {c["name"]: c["ttlDays"] for c in ret.get("classes", [])}

    # ---------- DB ----------
    db_ok = True
    alive = []; dead = []; wrows = []
    try:
        con = sqlite3.connect("file:" + DB.replace("\\", "/") + "?mode=ro", uri=True, timeout=30)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        for r in cur.execute("SELECT id,cwd,deleted_at,last_activity_at FROM sessions"):
            d = dict(r)
            (alive if d["deleted_at"] is None else dead).append(d)
        wrows = [dict(r) for r in cur.execute("SELECT path,last_opened_at FROM workspaces")]
        con.close()
    except Exception as e:
        db_ok = False; out["DB_ERR"] = str(e)
    out["DB_OK"] = db_ok
    alive_ids = set(r["id"] for r in alive)
    dead_ids = set(r["id"] for r in dead)
    alive_cwds = [r["cwd"] for r in alive]
    R_paths = set(norm(w["path"]) for w in wrows)
    out["R_count"] = len(wrows)
    out["alive_count"] = len(alive)
    out["dead_count"] = len(dead)

    # 磁盘一级目录真实大小写映射（cwd 归一化后是小写，必须映射回真实名字，
    # 否则 Claw / claw 之类会导致活会话数、显示名判定失真 → 可能误判候选）
    ew_names = {}
    for _d in os.listdir(EW):
        if os.path.isdir(os.path.join(EW, _d)):
            ew_names[norm(_d)] = _d

    def cwd_level1(cwd):
        if not cwd: return None
        n = norm(cwd)
        base = norm(EW) + os.sep
        if not n.startswith(base): return None
        rest = n[len(base):]
        part = rest.split(os.sep)[0]
        return ew_names.get(norm(part), part)

    # 活会话按一级目录归属
    alive_by_dir = {}
    for c in alive_cwds:
        k = cwd_level1(c)
        if k: alive_by_dir[k] = alive_by_dir.get(k, 0) + 1
    dead_by_dir = {}
    for r in dead:
        k = cwd_level1(r["cwd"])
        if k: dead_by_dir[k] = dead_by_dir.get(k, 0) + 1

    # ---------- 命名文件 ----------
    names_sha = sha256_file(NAMES)
    with open(NAMES, "r", encoding="utf-8") as f:
        nj = json.load(f)
    name_ws = nj.get("workspaces", {})
    name_count = len(name_ws)
    named_keys = set(norm(k) for k in name_ws.keys())
    # 归一到 EW 下的一级目录名
    named_dirs = set()
    for k in name_ws.keys():
        n = norm(k)
        base = norm(EW) + os.sep
        if n.startswith(base):
            part = n[len(base):].split(os.sep)[0]
            named_dirs.add(ew_names.get(norm(part), part))
    snap = os.path.join(RUNS, "names-snapshot", "workspace-display-names.json")
    snap_exists = os.path.isfile(snap)
    snap_match = snap_exists and (sha256_file(snap) == names_sha)
    out["names"] = {"count": name_count, "sha256": names_sha,
                    "mtime_ms": int(os.stat(NAMES).st_mtime * 1000),
                    "bytes": os.stat(NAMES).st_size,
                    "snapshot_exists": snap_exists, "snapshot_sha_match": snap_match,
                    "named_dirs": sorted(named_dirs)}

    # ---------- 验收前基线 ----------
    prj = dir_stat(os.path.join(WB, "projects"))
    sess = dir_stat(os.path.join(WB, "workspace", "sessions"))
    # 活会话 jsonl 路径（V3 基线）
    alive_jsonl = []
    for d in sorted(os.listdir(os.path.join(WB, "projects"))):
        pd = os.path.join(WB, "projects", d)
        if not os.path.isdir(pd): continue
        try:
            for fn in os.listdir(pd):
                if fn.endswith(".jsonl") and fn[:-6] in alive_ids:
                    alive_jsonl.append(os.path.join(pd, fn))
        except OSError:
            pass
    out["baseline"] = {
        "names_sha256": names_sha,
        "names_mtime_ms": int(os.stat(NAMES).st_mtime * 1000),
        "db_mtime_ms": int(os.stat(DB).st_mtime * 1000),
        "db_bytes": os.stat(DB).st_size,
        "workspaces_rows": len(wrows),
        "projects_bytes": prj[0], "projects_files": prj[1],
        "sessions_bytes": sess[0], "sessions_files": sess[1],
        "alive_jsonl_paths": alive_jsonl,
        "alive_jsonl_count": len(alive_jsonl),
    }
    # 磁盘可用空间
    for d in ("C", "E"):
        try:
            out["baseline"][d + "_free"] = shutil.disk_usage(d + ":\\").free
        except Exception as e:
            out["baseline"][d + "_free"] = None
    # 回收站
    for d in ("C", "E"):
        tot = 0; cnt = 0
        p = d + ":\\$Recycle.Bin"
        try:
            for root, dirs, fs in os.walk(p):
                for fn in fs:
                    try:
                        tot += os.stat(os.path.join(root, fn)).st_size; cnt += 1
                    except OSError: pass
        except OSError: pass
        out["baseline"]["recycle_" + d + "_bytes"] = tot
        out["baseline"]["recycle_" + d + "_files"] = cnt

    # ---------- 记忆体检（V5 基线） ----------
    mem = []
    for name in sorted(named_dirs | set(alive_by_dir.keys())):
        # 仅活空间：cwd ∈ R、目录存在、非 E 类
        dpath = os.path.join(EW, name)
        if norm(dpath) not in R_paths or not os.path.isdir(dpath): continue
        mf = os.path.join(dpath, ".workbuddy", "memory", "MEMORY.md")
        e = {"space": name, "dir": name}
        if os.path.isfile(mf):
            try:
                with open(mf, "r", encoding="utf-8") as f:
                    e["chars"] = len(f.read())
                e["mtime_ms"] = int(os.stat(mf).st_mtime * 1000)
            except Exception as ex:
                e["chars"] = -1; e["err"] = str(ex)
        else:
            e["chars"] = 0; e["mtime_ms"] = 0
        mdir = os.path.join(dpath, ".workbuddy", "memory")
        lf = 0; lc = 0
        if os.path.isdir(mdir):
            for fn in os.listdir(mdir):
                fp = os.path.join(mdir, fn)
                if os.path.isfile(fp) and fn != "MEMORY.md":
                    lf += 1
                    try:
                        with open(fp, "r", encoding="utf-8") as f: lc += len(f.read())
                    except Exception: pass
        e["log_files"] = lf; e["log_chars"] = lc
        mem.append(e)
    # 用户级 MEMORY.md
    user_mem = None
    for d in os.listdir(WB):
        if d.startswith("user-") and d.endswith("-personal"):
            fp = os.path.join(WB, d, "MEMORY.md")
            if os.path.isfile(fp):
                with open(fp, "r", encoding="utf-8") as f: user_mem = len(f.read())
    out["memory"] = {"spaces": mem, "user_chars": user_mem}
    # profile 缓存
    prof = {"bytes": 0, "files": 0, "mtime_ms": 0}
    pdir = os.path.join(WB, "memory")
    if os.path.isdir(pdir):
        for fn in os.listdir(pdir):
            fp = os.path.join(pdir, fn)
            if os.path.isfile(fp) and fn.endswith("_memory.md"):
                prof["bytes"] += os.stat(fp).st_size; prof["files"] += 1
                prof["mtime_ms"] = max(prof["mtime_ms"], int(os.stat(fp).st_mtime * 1000))
    out["profile_cache"] = prof
    out["baseline"]["memory_spaces"] = mem

    # ---------- 占用地图 ----------
    map_targets = [
        ("binaries", os.path.join(WB, "binaries")),
        ("workspace\\sessions", os.path.join(WB, "workspace", "sessions")),
        ("backups", os.path.join(WB, "backups")),
        ("plugins", os.path.join(WB, "plugins")),
        ("logs", os.path.join(WB, "logs")),
        ("projects", os.path.join(WB, "projects")),
        ("traces", os.path.join(WB, "traces")),
        ("shell-snapshots", os.path.join(WB, "shell-snapshots")),
        ("clipboard-images", os.path.join(WB, "clipboard-images")),
        ("audit-log", os.path.join(WB, "audit-log")),
        ("blobs", os.path.join(WB, "blobs")),
    ]
    idx_roots = ["file-tree-manifests", "file-history", "changes-detail", "changes-index", "artifact-index"]
    smap = []
    for name, p in map_targets:
        b, f, m, _ = dir_stat(p)
        smap.append({"name": name, "bytes": b, "files": f, "max_mtime": m})
    idx_b = idx_f = 0; idx_mx = 0
    for r in idx_roots:
        b, f, m, _ = dir_stat(os.path.join(WB, r))
        idx_b += b; idx_f += f; idx_mx = max(idx_mx, m)
    smap.append({"name": "编辑历史索引5类", "bytes": idx_b, "files": idx_f, "max_mtime": idx_mx})
    # 隔离区
    qroots = []
    for rr in q["roots"]:
        b, f, m, _ = dir_stat(rr["path"])
        qroots.append({"root": rr["path"], "volume": rr["volume"], "bytes": b, "files": f, "max_mtime": m})
    out["quarantine_roots"] = qroots
    smap.append({"name": "隔离区(合计)", "bytes": sum(x["bytes"] for x in qroots),
                 "files": sum(x["files"] for x in qroots), "max_mtime": 0})
    smap.sort(key=lambda x: -x["bytes"])
    out["space_map"] = smap

    # ---------- 回滚备份 Top5 会话 ----------
    sdir = os.path.join(WB, "workspace", "sessions")
    scope = set(["modify_backup", "snapfile", ".modify_backup_meta"])
    sids = []
    if os.path.isdir(sdir):
        for sid in os.listdir(sdir):
            sd = os.path.join(sdir, sid)
            if not os.path.isdir(sd): continue
            tb = tf = 0; mx = 0; extc = {}
            for sub in scope:
                sp = os.path.join(sd, sub)
                if not os.path.isdir(sp): continue
                for fp, sz, mt, _ in files_under(sp):
                    tb += sz; tf += 1; mx = max(mx, mt)
                    ext = os.path.splitext(fp)[1].lower() or "(无扩展)"
                    extc[ext] = extc.get(ext, 0) + 1
            if tf > 0:
                top_ext = max(extc.items(), key=lambda x: x[1])[0] if extc else "-"
                sids.append({"sid8": sid[:8], "sid": sid, "bytes": tb, "files": tf,
                             "last_write_ms": mx, "top_ext": top_ext})
    sids.sort(key=lambda x: -x["bytes"])
    # 所属空间名
    sid_space = {}
    for r in alive + dead:
        sid_space[r["id"]] = cwd_level1(r["cwd"]) or "-"
    ret_days = {c["name"]: c["ttlDays"] for c in ret.get("classes", [])}
    rb_days = ret_days.get("sessionRollback", 7)
    for s in sids:
        s["space"] = sid_space.get(s["sid"], "-")
        s["days_left"] = round(rb_days - (NOW - s["last_write_ms"]) / 86400000.0, 1)
    out["top5_sessions"] = sids[:5]
    out["session_rollback_total"] = {"bytes": sum(x["bytes"] for x in sids), "sessions": len(sids)}

    # ---------- 空间清单 + 2.7 候选 ----------
    inv = []
    cand = []
    for name in sorted(os.listdir(EW)):
        p = os.path.join(EW, name)
        if not os.path.isdir(p): continue
        if name in sq_exclude or name.startswith(".trash"):
            continue
        b, f, mx, _ = dir_stat(p)
        al = alive_by_dir.get(name, 0)
        dd = dead_by_dir.get(name, 0)
        in_R = norm(p) in R_paths
        has_name = name in named_dirs
        empty = (f == 0)
        # 24h 内是否有写入
        recent = (mx > 0 and (NOW - mx) < sq_written_ms)
        reasons = []
        is_cand = True
        if not in_R:
            is_cand = False; reasons.append("不在 workspaces 表")
        if al > 0:
            is_cand = False; reasons.append("有 %d 个活会话" % al)
        if has_name:
            is_cand = False; reasons.append("有显示名")
        if b > sq_max_bytes:
            is_cand = False; reasons.append("体积 %.2fMB > %.0fMB" % (b / MB, cr.get("maxDirMB", 1)))
        if recent:
            is_cand = False; reasons.append("24h 内有写入")
        e = {"dir": name, "path": p, "bytes": b, "files": f, "max_mtime": mx,
             "alive": al, "dead": dd, "in_R": in_R, "empty": empty,
             "has_name": has_name, "recent_write": recent,
             "is_candidate": is_cand, "reason": "候选" if is_cand else "；".join(reasons)}
        inv.append(e)
        if is_cand and sq_enabled:
            cand.append({"dir": name, "path": p, "bytes": b, "files": f,
                         "lastWrite": mx, "aliveSessions": al, "hasDisplayName": has_name,
                         "reason": "v9.3 方案C：0活会话+无显示名+24h无写入+<=%.0fMB" % cr.get("maxDirMB", 1)})
    out["inventory"] = inv
    out["candidates_27"] = cand
    out["candidate_total_bytes"] = sum(c["bytes"] for c in cand)
    out["empty_shells"] = [e["dir"] for e in inv if e["empty"]]

    # ---------- cwd 告警 ----------
    cw = []
    for r in alive:
        c = r["cwd"]
        if not c: continue
        if not os.path.isdir(c):
            n = norm(c)
            if n.startswith(norm(EW) + os.sep):
                cw.append({"sid8": r["id"][:8], "cwd": c, "class": "A 类（自家空间被移走/改名）"})
            else:
                cw.append({"sid8": r["id"][:8], "cwd": c, "class": "E 类（外部临时目录，微信自清）"})
    out["cwd_warnings"] = cw

    # ---------- 已删会话占用 ----------
    dead_occ = {"count": len(dead), "projects_bytes": 0, "sessions_bytes": 0, "index_bytes": 0, "items": []}
    for d in sorted(os.listdir(os.path.join(WB, "projects"))):
        pd = os.path.join(WB, "projects", d)
        if not os.path.isdir(pd): continue
        try:
            for fn in os.listdir(pd):
                if fn.endswith(".jsonl") and fn[:-6] in dead_ids:
                    dead_occ["projects_bytes"] += os.stat(os.path.join(pd, fn)).st_size
        except OSError: pass
    for sid in dead_ids:
        sd = os.path.join(sdir, sid)
        if os.path.isdir(sd):
            b, f, m, _ = dir_stat(sd); dead_occ["sessions_bytes"] += b
    idx_resid = {}
    for r in idx_roots:
        rp = os.path.join(WB, r)
        if not os.path.isdir(rp): continue
        c = 0; bb = 0
        for e in os.listdir(rp):
            stem = e[:-5] if e.endswith(".json") else e
            if stem in dead_ids:
                c += 1
                ep = os.path.join(rp, e)
                if os.path.isdir(ep):
                    b, f, m, _ = dir_stat(ep); bb += b
                elif os.path.isfile(ep):
                    bb += os.stat(ep).st_size
        idx_resid[r] = {"count": c, "bytes": bb}
        dead_occ["index_bytes"] += bb
    dead_occ["index_residual"] = idx_resid
    out["dead_sessions"] = dead_occ
    # 索引对齐
    align = {"alive_count": len(alive), "indexes": {}}
    for r in idx_roots:
        rp = os.path.join(WB, r)
        cnt = 0; res = 0
        if os.path.isdir(rp):
            for e in os.listdir(rp):
                cnt += 1
                stem = e[:-5] if e.endswith(".json") else e
                if stem in dead_ids: res += 1
        align["indexes"][r] = {"items": cnt, "dead_residual": res}
    out["index_alignment"] = align

    # ---------- 无引用上传图（只读统计） ----------
    corpus = []
    cbytes = 0
    cap = 300 * 1024 * 1024
    for pd_name in sorted(os.listdir(os.path.join(WB, "projects"))):
        pd = os.path.join(WB, "projects", pd_name)
        if not os.path.isdir(pd): continue
        try:
            for fn in os.listdir(pd):
                if fn.endswith(".jsonl") and fn[:-6] in alive_ids:
                    fp = os.path.join(pd, fn)
                    try:
                        sz = os.stat(fp).st_size
                        if cbytes + sz > cap: continue
                        with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                            t = f.read()
                        corpus.append(t); cbytes += sz
                    except OSError: pass
        except OSError: pass
    for r in ("local_storage", "storage"):
        rp = os.path.join(WB, r)
        for root, dirs, fs in os.walk(rp):
            for fn in fs:
                fp = os.path.join(root, fn)
                try:
                    sz = os.stat(fp).st_size
                    if sz > 2 * 1024 * 1024 or cbytes + sz > cap: continue
                    with open(fp, "r", encoding="utf-8", errors="ignore") as f: t = f.read()
                    corpus.append(t); cbytes += sz
                except OSError: pass
    big = "\n".join(corpus)
    blob_root = os.path.join(WB, "blobs")
    unreferenced = 0; unref_bytes = 0; blob_total = 0; blob_files = 0
    for root, dirs, fs in os.walk(blob_root):
        for fn in fs:
            fp = os.path.join(root, fn)
            try: sz = os.stat(fp).st_size
            except OSError: continue
            blob_total += 1; blob_files += 1
            stem = os.path.splitext(fn)[0]
            key = stem[:16] if len(stem) >= 16 else stem
            if key and key not in big:
                unreferenced += 1; unref_bytes += sz
    out["unreferenced_blobs"] = {"total": blob_total, "unreferenced": unreferenced,
                                 "unreferenced_bytes": unref_bytes, "corpus_bytes": cbytes}

    # ---------- 隔离区批次判定（2.5） ----------
    batches = []
    release_plan = []
    if db_ok or True:  # 2.5 不依赖会话数据
        for rr in q["roots"]:
            root = rr["path"]
            if not os.path.isdir(root): continue
            for d in sorted(os.listdir(root)):
                bp = os.path.join(root, d)
                if not os.path.isdir(bp): continue
                if not re.fullmatch(r"\d{8}", d):
                    batches.append({"batch": d, "root": root, "eligible": False,
                                    "reason": "名字不匹配 ^\\d{8}$（红线，不动）"})
                    continue
                if not under(bp, root):
                    batches.append({"batch": d, "root": root, "eligible": False, "reason": "refused 路径断言失败"})
                    continue
                # 找 manifest（一级或二级）
                mpath = None; mj = None
                m1 = os.path.join(bp, "manifest.json")
                mlist = [m1]
                try:
                    for sub in os.listdir(bp):
                        m2 = os.path.join(bp, sub, "manifest.json")
                        if os.path.isfile(m2): mlist.append(m2)
                except OSError: pass
                for mp in mlist:
                    if os.path.isfile(mp):
                        try:
                            with open(mp, "r", encoding="utf-8") as f: j = json.load(f)
                            if isinstance(j.get("items"), list) and len(j["items"]) > 0:
                                mpath = mp; mj = j; break
                        except Exception: pass
                b, f, mx, _ = dir_stat(bp)
                e = {"batch": d, "root": root, "files": f, "bytes": b,
                     "manifest_path": mpath, "manifest_ok": mj is not None,
                     "manifest_createdAt": (mj or {}).get("createdAt"),
                     "manifest_items": len(mj.get("items", [])) if mj else 0,
                     "manifest_reason": (mj or {}).get("reason")}
                # 到期时间：目录名本地 00:00 与 createdAt 取较晚
                try:
                    d0 = datetime.datetime.strptime(d, "%Y%m%d")
                    dir_ms = int(d0.timestamp() * 1000)
                except Exception:
                    dir_ms = None
                ca = (mj or {}).get("createdAt")
                ca_ms = int(ca) if isinstance(ca, (int, float)) else None
                cands = [x for x in (dir_ms, ca_ms) if x is not None]
                if not cands:
                    e["eligible"] = False; e["reason"] = "算不得到期时间 → 需你确认"; batches.append(e); continue
                base_ms = max(cands)
                age_ms = NOW - base_ms
                e["base_ms"] = base_ms; e["age_hours"] = round(age_ms / 3600000.0, 1)
                e["remaining_days"] = round((q_ttl_ms - age_ms) / 86400000.0, 1)
                # 近期写入
                e["recent_write"] = (mx > 0 and (NOW - mx) < q_guard_ms)
                e["max_mtime"] = mx
                reasons = []
                if age_ms < q_ttl_ms: reasons.append("未到期 剩 %.1f 天" % e["remaining_days"])
                if e["recent_write"]: reasons.append("24h 内有写入 延后")
                if mj is None: reasons.append("缺合法 manifest 或 items 为空")
                if reasons:
                    e["eligible"] = False; e["reason"] = "；".join(reasons)
                else:
                    e["eligible"] = True; e["reason"] = "五条全满足 → 到期自动释放"
                batches.append(e)
                if e["eligible"]:
                    flist = []
                    for fp, sz, mt, ism in files_under(bp):
                        flist.append({"path": fp, "size": sz, "mtime": mt, "is_manifest": ism})
                    # 子目录（用于三步删空目录）
                    dl = dirs_under(bp)
                    release_plan.append({"batch": d, "root": root, "bytes": b,
                                         "files": f, "ageHours": e["age_hours"],
                                         "manifestOk": True, "manifestPath": mpath,
                                         "items": flist, "dirs": dl, "batchPath": bp})
    out["quarantine_batches"] = batches
    out["release_plan_count"] = len(release_plan)

    # ---------- retention 冻结计划（2.6） ----------
    retention_plan = []
    retention_summary = {}
    names_snapshot_need = ret_enabled or sq_enabled
    if ret_enabled and db_ok:
        # 会话正文 sid 集合
        jsonl_sids = set()
        for pd_name in os.listdir(os.path.join(WB, "projects")):
            pd = os.path.join(WB, "projects", pd_name)
            if os.path.isdir(pd):
                for fn in os.listdir(pd):
                    if fn.endswith(".jsonl"): jsonl_sids.add(fn[:-6])
        excl = set(ret.get("exclusions", []))
        for c in ret.get("classes", []):
            cname = c["name"]; ttl = c.get("ttlDays", 7) * 86400000
            entries = []
            if cname == "sessionRollback":
                root = os.path.join(WB, *c["root"].split("\\"))
                sc = set(c.get("scope", []))
                for sid in sorted(os.listdir(root)):
                    sd = os.path.join(root, sid)
                    if not os.path.isdir(sd): continue
                    sdirs = [os.path.join(sd, s) for s in sc if os.path.isdir(os.path.join(sd, s))]
                    if not sdirs: continue
                    fl = []; mx = 0; tb = 0
                    for sp in sdirs:
                        for fp, sz, mt, _ in files_under(sp):
                            fl.append({"path": fp, "size": sz, "mtime": mt}); mx = max(mx, mt); tb += sz
                    if not fl: continue
                    # 会话目录整体最后写入（保守）
                    sb, sf, smx, _ = dir_stat(sd)
                    lastw = max(mx, smx)
                    age = NOW - lastw
                    e = {"class": cname, "entry": sid[:8], "sid": sid, "bytes": tb, "files": len(fl),
                         "last_write_ms": lastw, "age_days": round(age / 86400000.0, 1),
                         "days_left": round((ttl - age) / 86400000.0, 1),
                         "files_list": fl}
                    # 七条保护
                    prot = []
                    if sid[:8] in excl: prot.append("exclusions 白名单")
                    if age < ttl: prot.append("未到期")
                    if (NOW - smx) < active_ms: prot.append("24h 内有写入")
                    if sid not in jsonl_sids: prot.append("会话正文不存在")
                    # 每个待删文件必须落在三个具名子目录之一内（any），不是同时落在全部（all）
                    if not all(any(under(x["path"], sp) for sp in sdirs) for x in fl):
                        prot.append("refused 路径断言失败")
                    e["protected"] = bool(prot); e["protect_reasons"] = prot
                    if not prot:
                        retention_plan.append({"class": cname, "entry": sid[:8],
                                               "ageDays": e["age_days"], "items": fl})
                    entries.append(e)
            elif cname == "backupSnapshots":
                root = os.path.join(WB, c["root"])
                for en in sorted(os.listdir(root)):
                    ep = os.path.join(root, en)
                    fl = []; mx = 0; tb = 0
                    if os.path.isdir(ep):
                        for fp, sz, mt, _ in files_under(ep):
                            fl.append({"path": fp, "size": sz, "mtime": mt}); mx = max(mx, mt); tb += sz
                    elif os.path.isfile(ep):
                        st = os.stat(ep); fl = [{"path": ep, "size": st.st_size, "mtime": int(st.st_mtime * 1000)}]
                        mx = fl[0]["mtime"]; tb = fl[0]["size"]
                    if not fl: continue
                    age = NOW - mx
                    e = {"class": cname, "entry": en, "bytes": tb, "files": len(fl),
                         "last_write_ms": mx, "age_days": round(age / 86400000.0, 1),
                         "days_left": round((ttl - age) / 86400000.0, 1)}
                    prot = []
                    if age < ttl: prot.append("未到期")
                    if (NOW - mx) < active_ms: prot.append("24h 内有写入")
                    if not all(under(x["path"], root) for x in fl): prot.append("refused 路径断言失败")
                    e["protected"] = bool(prot); e["protect_reasons"] = prot
                    if not prot:
                        retention_plan.append({"class": cname, "entry": en,
                                               "ageDays": e["age_days"], "items": fl})
                    entries.append(e)
            elif cname == "editHistoryIndexes":
                for r in c.get("roots", []):
                    root = os.path.join(WB, r)
                    if not os.path.isdir(root): continue
                    for en in sorted(os.listdir(root)):
                        ep = os.path.join(root, en)
                        fl = []; mx = 0; tb = 0
                        if os.path.isdir(ep):
                            for fp, sz, mt, _ in files_under(ep):
                                fl.append({"path": fp, "size": sz, "mtime": mt}); mx = max(mx, mt); tb += sz
                        elif os.path.isfile(ep):
                            st = os.stat(ep); fl = [{"path": ep, "size": st.st_size, "mtime": int(st.st_mtime * 1000)}]
                            mx = fl[0]["mtime"]; tb = fl[0]["size"]
                        if not fl: continue
                        age = NOW - mx
                        e = {"class": cname, "entry": r + "\\" + en, "bytes": tb, "files": len(fl),
                             "last_write_ms": mx, "age_days": round(age / 86400000.0, 1),
                             "days_left": round((ttl - age) / 86400000.0, 1)}
                        prot = []
                        if age < ttl: prot.append("未到期")
                        if (NOW - mx) < active_ms: prot.append("24h 内有写入")
                        if not all(under(x["path"], root) for x in fl): prot.append("refused 路径断言失败")
                        e["protected"] = bool(prot); e["protect_reasons"] = prot
                        if not prot:
                            retention_plan.append({"class": cname, "entry": r + "\\" + en,
                                                   "ageDays": e["age_days"], "items": fl})
                        entries.append(e)
            due = [e for e in entries if not e["protected"]]
            notdue = [e for e in entries if e["protected"]]
            prot_reasons = {}
            for e in notdue:
                for p in e["protect_reasons"]:
                    prot_reasons[p] = prot_reasons.get(p, 0) + 1
            retention_summary[cname] = {
                "ttlDays": c.get("ttlDays", 7),
                "due_count": len(due), "due_bytes": sum(e["bytes"] for e in due),
                "notdue_count": len(notdue), "notdue_bytes": sum(e["bytes"] for e in notdue),
                "nearest_days_left": min([e["days_left"] for e in notdue], default=None),
                "protect_reasons": prot_reasons,
            }
    out["retention_plan_count"] = len(retention_plan)
    out["retention_summary"] = retention_summary

    # ---------- 缓存白名单冻结计划（第 2 节） ----------
    cache_plan = []
    whitelist = pol.get("autoDeleteWhitelist", [])
    for w in whitelist:
        rp = os.path.join(WB, *w["path"].split("\\"))
        ttl_ms = w.get("ttlHours", 24) * 3600000
        skip = set()
        if w["name"] == "logs":
            skip = {"Crash-Log"}  # Crash-Log 单独轮转
        for fp, sz, mt, _ in files_under(rp, skip_dir_names=skip):
            if not under(fp, rp):
                continue
            if (NOW - mt) >= ttl_ms and (NOW - mt) >= active_ms:
                cache_plan.append({"path": fp, "size": sz, "mtime": mt, "rule": w["name"]})
    # Crash-Log 轮转：只留最近 crashLogKeep 个崩溃包
    cl = os.path.join(WB, "logs", "Crash-Log")
    crash_keep = pol.get("crashLogKeep", 3)
    crash_out = {"kept": 0, "removed": 0, "files": []}
    if os.path.isdir(cl):
        packs = []
        for fp, sz, mt, _ in files_under(cl):
            if re.match(r"crash-report-", os.path.basename(fp)):
                packs.append((fp, sz, mt))
        packs.sort(key=lambda x: -x[2])
        for i, (fp, sz, mt) in enumerate(packs):
            if i >= crash_keep and (NOW - mt) >= active_ms:
                cache_plan.append({"path": fp, "size": sz, "mtime": mt, "rule": "Crash-Log"})
                crash_out["removed"] += 1
            else:
                crash_out["kept"] += 1
            crash_out["files"].append({"name": os.path.basename(fp), "mtime": mt})
    out["crash_log"] = crash_out
    # 顶层 failover.json.*.tmp / *.part
    for fn in os.listdir(WB):
        fp = os.path.join(WB, fn)
        if not os.path.isfile(fp): continue
        match = re.match(r"failover\.json\..*\.tmp$", fn) or fn.endswith(".part")
        if match:
            st = os.stat(fp)
            if (NOW - int(st.st_mtime * 1000)) >= 86400000:
                cache_plan.append({"path": fp, "size": st.st_size,
                                   "mtime": int(st.st_mtime * 1000), "rule": "topTemp"})
    out["cache_plan_count"] = len(cache_plan)
    out["cache_plan_by_rule"] = {}
    for x in cache_plan:
        r = x["rule"]
        d = out["cache_plan_by_rule"].setdefault(r, {"files": 0, "bytes": 0})
        d["files"] += 1; d["bytes"] += x["size"]

    # ---------- 冻结四份计划到 cleanup-runs ----------
    plan_paths = {}
    p1 = os.path.join(RUNS, "plan-%s.json" % ts)
    with open(p1, "w", encoding="utf-8") as f: json.dump(cache_plan, f, ensure_ascii=False)
    plan_paths["cache"] = p1
    p2 = os.path.join(RUNS, "release-%s.json" % ts)
    with open(p2, "w", encoding="utf-8") as f: json.dump(release_plan, f, ensure_ascii=False)
    plan_paths["release"] = p2
    p3 = os.path.join(RUNS, "retention-%s.json" % ts)
    with open(p3, "w", encoding="utf-8") as f: json.dump(retention_plan, f, ensure_ascii=False)
    plan_paths["retention"] = p3
    p4 = os.path.join(RUNS, "spaces-%s.json" % ts)
    with open(p4, "w", encoding="utf-8") as f: json.dump(cand, f, ensure_ascii=False)
    plan_paths["spaces"] = p4
    out["plan_paths"] = plan_paths
    out["names_snapshot_need"] = names_snapshot_need

    with open(os.path.join(TMP, "scan.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    with open(os.path.join(TMP, "baseline.json"), "w", encoding="utf-8") as f:
        json.dump(out["baseline"], f, ensure_ascii=False, indent=1)
    # 控制台只输出 ASCII 摘要
    print("SCAN_OK ts=%s cache=%d release=%d retention=%d spaces=%d" %
          (ts, len(cache_plan), len(release_plan), len(retention_plan), len(cand)))

if __name__ == "__main__":
    main()
