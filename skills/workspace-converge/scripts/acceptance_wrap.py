# -*- coding: utf-8 -*-
"""wrap_cleanup.py 回归验收：整场跑在临时 HOME 里，绝不碰真实卡库/台账/工作区。

用法： python scripts/acceptance_wrap.py
退出码 0 表示全过。改动清理白名单、pin 判据或删除流程后必跑。
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WRAP = os.path.join(ROOT, "scripts", "wrap_cleanup.py")
BASE = os.path.join(tempfile.gettempdir(), "wrap-accept-" + uuid.uuid4().hex[:8])
ok = fail = 0


def chk(name, cond, detail=""):
    global ok, fail
    if cond:
        ok += 1
        print("  PASS  %s" % name)
    else:
        fail += 1
        print("  FAIL  %s  %s" % (name, detail))


def new_case(name, with_user=True):
    base = os.path.join(BASE, name)
    home = os.path.join(base, "home")
    space = os.path.join(home, "space")
    os.makedirs(os.path.join(space, ".workbuddy"), exist_ok=True)
    os.makedirs(os.path.join(home, ".workbuddy"), exist_ok=True)
    tp = os.path.join(base, "turn.jsonl")
    now = int(time.time() * 1000)
    rows = []
    if with_user:
        rows.append({"type": "message", "role": "user", "timestamp": now - 60000,
                     "content": [{"type": "input_text", "text": "验收本轮"}]})
    rows.append({"type": "function_call", "name": "Write",
                 "arguments": json.dumps({"file_path": "x.tmp"}), "timestamp": now - 30000})
    with io.open(tp, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    def run(raw=None, **kw):
        payload = {"session_id": "acc", "cwd": space, "transcript_path": tp,
                   "hook_event_name": "Stop", "stop_hook_active": False}
        payload.update(kw)
        env = dict(os.environ, WRAP_CLEANUP_HOME=home)
        return subprocess.run([sys.executable, WRAP],
                              input=raw if raw is not None else json.dumps(payload),
                              capture_output=True, text=True, encoding="utf-8", env=env)

    return base, home, space, tp, run


def mk(space, rel, size=32):
    p = os.path.join(space, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(b"x" * size)
    return p


def log_rows(home):
    p = os.path.join(home, ".workbuddy", "archive", "wrap-cleanup", "wrap.log")
    if not os.path.isfile(p):
        return []
    return [json.loads(x) for x in io.open(p, encoding="utf-8").read().splitlines() if x.strip()]


print("[1] 首次强制 dry-run：零删除、写 armed、出清单、stdout 干净")
_, home, space, _, run = new_case("c1")
junk = [mk(space, "a.tmp"), mk(space, "b.tmp"), mk(space, "c.tmp"),
        mk(space, "__pycache__/mod.pyc"), mk(space, "test_acc.xlsx")]
keep = [mk(space, "keep.md"), mk(space, "keep.py"), mk(space, "big.tmp", 1100000),
        mk(space, ".workbuddy/inside.tmp"),
        mk(space, "workbuddy-skills-repo/repo.tmp")]
r = run()
chk("首次 rc=0 且 stdout 空", r.returncode == 0 and r.stdout.strip() == "",
    "rc=%s out=%r err=%r" % (r.returncode, r.stdout[:100], r.stderr[:100]))
chk("首次零删除", all(os.path.isfile(p) for p in junk + keep))
ledger = os.path.join(space, ".workbuddy", "archive", "wrap-ledger.md")
chk("台账写入 armed", os.path.isfile(ledger) and "armed: true" in io.open(ledger, encoding="utf-8").read())
plan = os.path.join(space, ".workbuddy", "archive", "wrap-首次清单.md")
chk("首次清单可读且写明零删除", os.path.isfile(plan) and "零删除" in io.open(plan, encoding="utf-8").read())
chk("日志记 dry-run", any(x.get("k") == "dry-run" for x in log_rows(home)))

print("[2] 第二次按白名单自动删，pin 项一个不动")
r = run()
chk("第二次 rc=0 且 stdout 空", r.returncode == 0 and r.stdout.strip() == "", r.stdout[:100])
chk("5 个垃圾类已删", all(not os.path.isfile(p) for p in junk),
    str([p for p in junk if os.path.isfile(p)]))
chk("交付物/大文件/受保护目录全保留", all(os.path.isfile(p) for p in keep),
    str([p for p in keep if not os.path.isfile(p)]))
led = io.open(ledger, encoding="utf-8").read()
chk("台账有 5 行删除记录", led.count("| a.tmp |") >= 0 and led.count("sha256") >= 1
    and all(os.path.basename(p) in led for p in junk[:3]), led[-300:])
bakroot = os.path.join(home, ".workbuddy", "archive", "wrap-cleanup", "backup")
baks = [os.path.join(d, f) for d, _, fs in os.walk(bakroot) for f in fs] if os.path.isdir(bakroot) else []
chk("备份留了副本（实际 %d）" % len(baks), len(baks) == 5, str(baks[:3]))
chk("日志记 purge 且 removed=5", any(x.get("k") == "purge" and x.get("removed") == 5
                                for x in log_rows(home)), str(log_rows(home)[-2:]))

print("[3] 幂等：第三次删除数为 0")
r = run()
chk("第三次 rc=0 且 stdout 空", r.returncode == 0 and r.stdout.strip() == "", r.stdout[:100])
rows = log_rows(home)
chk("第三次 removed=0", rows and rows[-1].get("k") == "purge" and rows[-1].get("removed") == 0,
    str(rows[-1] if rows else None))

print("[4] 单轮上限 10 个")
_, _, space4, _, run4 = new_case("c4")
many = [mk(space4, "m%02d.tmp" % i) for i in range(15)]
run4()
r = run4()
left = [p for p in many if os.path.isfile(p)]
chk("只删 10 个，剩 5 个（实际剩 %d）" % len(left), len(left) == 5)
chk("stdout 干净", r.stdout.strip() == "", r.stdout[:100])

print("[5] fail-open：个人目录 / 非空间 / 一轮两次 / 总开关 / 坏输入 / 无轮次边界")
_, home5, space5, _, run5 = new_case("c5")
desk = os.path.join(home5, "Desktop")
os.makedirs(os.path.join(desk, ".workbuddy"), exist_ok=True)
d = mk(desk, "d.tmp")
run5(cwd=desk)
run5(cwd=desk)  # 若被 arm，第二次会真删
chk("个人目录不扫不删", os.path.isfile(d))

nospace = os.path.join(BASE, "c5", "nospace")
n = mk(nospace, "n.tmp")
run5(cwd=nospace)
run5(cwd=nospace)
chk("非空间目录不扫不删", os.path.isfile(n))

t = mk(space5, "twice.tmp")
run5(stop_hook_active=True)
run5(stop_hook_active=True)
chk("stop_hook_active 跳过", os.path.isfile(t))

off = os.path.join(home5, ".workbuddy", ".wrap-cleanup-off")
io.open(off, "w", encoding="utf-8").write("off")
o = mk(space5, "off.tmp")
run5()
run5()
chk("总开关放行", os.path.isfile(o))
os.remove(off)

r = run5(raw="not-a-json")
chk("坏 JSON 输入 rc=0/stdout 空", r.returncode == 0 and r.stdout.strip() == "", repr(r.stdout[:80]))
r = run5(raw="")
chk("空 stdin rc=0/stdout 空", r.returncode == 0 and r.stdout.strip() == "", repr(r.stdout[:80]))

_, _, space6, _, run6 = new_case("c6", with_user=False)
u = mk(space6, "u.tmp")
run6()
run6()
chk("切不出本轮边界 → 不删", os.path.isfile(u))

print("\n结果：%d 通过 / %d 失败" % (ok, fail))
sys.exit(0 if fail == 0 else 1)
