# -*- coding: utf-8 -*-
"""只读对账：压缩/中断后，按冻结计划逐条回读磁盘真实状态。
输出四类计划各自 planned / remaining(存在且 size+mtime 一致) / missing / changed，
以及关键目录体积、命名文件 SHA、锁 pid 存活。绝不删改任何对象。"""
import os, json, hashlib, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
WB = os.environ.get("WB_CLEAN_HOME", r"C:\Users\Administrator\.workbuddy")
TMP = os.path.abspath(os.environ.get("WB_CLEAN_WORKDIR", os.path.join(HERE, "..", ".work")))
EW = os.environ.get("WB_CLEAN_EW", r"E:\WorkBuddy")
QR_E = r"E:\WorkBuddy\.trash-quarantine"
QR_C = r"C:\Users\Administrator\.cleanup-quarantine"
MB = 1024.0 * 1024.0

def load(p):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)

def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()

def dstat(path):
    tb = tf = 0
    if not os.path.isdir(path):
        return (tb, tf)
    stack = [path]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    if e.is_dir(follow_symlinks=False):
                        stack.append(e.path)
                    else:
                        try:
                            tb += e.stat(follow_symlinks=False).st_size; tf += 1
                        except OSError:
                            pass
        except OSError:
            pass
    return (tb, tf)

def free(d):
    try: return shutil.disk_usage(d + ":\\").free
    except Exception: return None

def recycle(d):
    tot = cnt = 0
    p = d + ":\\$Recycle.Bin"
    try:
        for root, dirs, fs in os.walk(p):
            for fn in fs:
                try:
                    tot += os.stat(os.path.join(root, fn)).st_size; cnt += 1
                except OSError: pass
    except OSError: pass
    return (tot, cnt)

def classify(items):
    """items: list of dict with path/size/mtime"""
    st = {"planned": 0, "remain": 0, "missing": 0, "changed": 0, "remain_bytes": 0, "missing_bytes": 0}
    for it in items:
        st["planned"] += 1
        p = it["path"]
        if not os.path.lexists(p):
            st["missing"] += 1; st["missing_bytes"] += it["size"]; continue
        try: s = os.stat(p)
        except OSError:
            st["missing"] += 1; st["missing_bytes"] += it["size"]; continue
        if s.st_size != it["size"] or abs(int(s.st_mtime * 1000) - it["mtime"]) > 2000:
            st["changed"] += 1; continue
        st["remain"] += 1; st["remain_bytes"] += it["size"]
    return st

def main():
    s = load(os.path.join(TMP, "scan.json"))
    ts = s["ts"]
    out = {"ts": ts, "scan_at": s.get("now_ms")}
    out["done_marker"] = os.path.exists(os.path.join(TMP, "exec-%s.done" % ts))
    out["result_json"] = os.path.exists(os.path.join(TMP, "result.json"))

    # 命名文件
    names = os.path.join(WB, "workspace-display-names.json")
    snap = os.path.join(WB, "cleanup-runs", "names-snapshot", "workspace-display-names.json")
    out["names"] = {"src_sha": sha(names), "snap_exists": os.path.exists(snap),
                    "snap_sha": sha(snap) if os.path.exists(snap) else None}

    # 锁 pid
    lk = os.path.join(WB, "cleanup.lock")
    lock = load(lk) if os.path.exists(lk) else {}
    out["lock"] = lock
    try:
        r = subprocess.run(["tasklist", "/FI", "PID eq %s" % lock.get("pid"), "/NH"],
                           capture_output=True, timeout=15)
        r.stdout = (r.stdout or b"").decode("gbk", errors="ignore")
        out["lock_pid_alive"] = str(lock.get("pid")) in (r.stdout or "")
        out["lock_tasklist"] = (r.stdout or "").strip()[:200]
    except Exception as e:
        out["lock_pid_alive"] = "unknown:%s" % e

    # 四类计划
    pp = s["plan_paths"]
    cache = load(pp["cache"])
    out["cache"] = classify(cache)

    rel = load(pp["release"])
    rit = []
    for b in rel:
        rit.extend(b["items"])
    out["release"] = classify(rit)
    out["release_batches"] = [{"batch": b["batch"], "root": b["root"],
                               "batch_exists": os.path.isdir(b["batchPath"]),
                               "manifest_exists": os.path.exists(b["manifestPath"]),
                               "planned_files": b["files"], "planned_bytes": b["bytes"]} for b in rel]

    ret = load(pp["retention"])
    rrit = []
    byc = {}
    for e in ret:
        rrit.extend(e["items"])
        c = e["class"]
        d = byc.setdefault(c, {"entries": 0, "items": []})
        d["entries"] += 1; d["items"].extend(e["items"])
    out["retention"] = classify(rrit)
    out["retention_by_class"] = {k: {"entries": v["entries"], **classify(v["items"])} for k, v in byc.items()}

    sp = load(pp["spaces"])
    out["spaces"] = [{"dir": c["dir"], "path": c["path"],
                      "src_exists": os.path.isdir(c["path"]),
                      "bytes": c["bytes"], "files": c["files"]} for c in sp]
    out["space_batch_exists"] = os.path.isdir(os.path.join(QR_E, "20261116"))

    # 关键目录体积
    keys = {
        "logs": os.path.join(WB, "logs"),
        "traces": os.path.join(WB, "traces"),
        "shell-snapshots": os.path.join(WB, "shell-snapshots"),
        "productSpill": os.path.join(WB, "cache", "conversation-product-spill"),
        "clipboard-images": os.path.join(WB, "clipboard-images"),
        "audit-log": os.path.join(WB, "audit-log"),
        "workspace_sessions": os.path.join(WB, "workspace", "sessions"),
        "backups": os.path.join(WB, "backups"),
        "file-tree-manifests": os.path.join(WB, "file-tree-manifests"),
        "file-history": os.path.join(WB, "file-history"),
        "changes-detail": os.path.join(WB, "changes-detail"),
        "changes-index": os.path.join(WB, "changes-index"),
        "artifact-index": os.path.join(WB, "artifact-index"),
        "QR_C": QR_C, "QR_E": QR_E,
        "QR_C_batch": os.path.join(QR_C, "20261104"),
    }
    out["dirs"] = {}
    for k, p in keys.items():
        b, f = dstat(p)
        out["dirs"][k] = {"bytes": b, "files": f, "MB": round(b / MB, 2)}

    # 磁盘与回收站
    out["disk"] = {"C_free": free("C"), "E_free": free("E")}
    for d in ("C", "E"):
        b, f = recycle(d)
        out["disk"]["recycle_%s" % d] = b
        out["disk"]["recycle_%s_files" % d] = f

    # baseline.json 结构
    bl_path = os.path.join(TMP, "baseline.json")
    if os.path.exists(bl_path):
        bl = load(bl_path)
        out["baseline_keys"] = list(bl.keys())
        out["baseline"] = bl

    with open(os.path.join(TMP, "status.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    # 控制台摘要
    print("TS=%s done=%s result=%s" % (ts, out["done_marker"], out["result_json"]))
    print("NAMES match=%s" % (out["names"]["src_sha"] == out["names"]["snap_sha"]))
    print("LOCK pid=%s alive=%s" % (out["lock"].get("pid"), out["lock_pid_alive"]))
    for k in ("cache", "release", "retention"):
        v = out[k]
        print("%-10s planned=%-6d remain=%-6d missing=%-6d changed=%-4d remain_MB=%.2f missing_MB=%.2f" % (
            k, v["planned"], v["remain"], v["missing"], v["changed"],
            v["remain_bytes"] / MB, v["missing_bytes"] / MB))
    for k, v in out["retention_by_class"].items():
        print("   %-20s entries=%-4d planned=%-6d remain=%-6d missing=%-6d" % (
            k, v["entries"], v["planned"], v["remain"], v["missing"]))
    print("RELEASE batches:", out["release_batches"])
    print("SPACES:", out["spaces"], "batch20261116=", out["space_batch_exists"])
    print("DIRS MB:", {k: v["MB"] for k, v in out["dirs"].items()})
    print("DISK C_free_GB=%.3f E_free_GB=%.3f recycle_C_MB=%.2f recycle_E_MB=%.2f" % (
        out["disk"]["C_free"] / (1024**3), out["disk"]["E_free"] / (1024**3),
        out["disk"]["recycle_C"] / MB, out["disk"]["recycle_E"] / MB))
    print("BASELINE_KEYS:", out.get("baseline_keys"))

if __name__ == "__main__":
    main()
