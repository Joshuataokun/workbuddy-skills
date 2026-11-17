#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""memory_check.py 回归验收 · 整场跑在临时 HOME 与临时空间，绝不碰真实记忆文件。"""
from __future__ import annotations

import hashlib
import io
import os
import re
import subprocess
import sys
import tempfile
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MC = os.path.join(ROOT, "scripts", "memory_check.py")
BASE = os.path.join(tempfile.gettempdir(), "mem-accept-" + uuid.uuid4().hex[:8])
HOME = os.path.join(BASE, "home")
WS = os.path.join(BASE, "ws")
USER_MEM = os.path.join(HOME, ".workbuddy", "user-test", "MEMORY.md")
SPACE_MEM = os.path.join(WS, ".workbuddy", "memory", "MEMORY.md")
DAY_LOG = os.path.join(WS, ".workbuddy", "memory", "2026-11-18.md")

PASS = FAIL = 0


def write(p, text):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with io.open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def md5(p):
    return hashlib.md5(open(p, "rb").read()).hexdigest()


def run(args, env=None):
    e = dict(os.environ, MEMORY_CHECK_HOME=HOME)
    if env:
        e.update(env)
    return subprocess.run([sys.executable, MC] + args, capture_output=True,
                          text=True, encoding="utf-8", env=e)


def chk(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  PASS  " + name)
    else:
        FAIL += 1
        print("  FAIL  " + name + ("  " + str(extra)[:160] if extra else ""))


def setup(user_text, space_text, log_text=""):
    write(USER_MEM, user_text)
    write(SPACE_MEM, space_text)
    write(DAY_LOG, log_text or "# 日志\n")


print("[1] 预算与只读")
setup("# 用户记忆\n\n- 一条很短的口径，用来测试未到阈值不报警。\n",
      "# 空间记忆\n\n- 另一条很短的口径，同样未到阈值。\n")
r = run(["status", "--workspace", WS])
chk("未到 80% 时 status 输出 OK", r.returncode == 0 and "OK" in r.stdout, r.stdout)

long_user = "# 用户记忆\n\n" + "- 这是一条足够长的长期口径用来把字符数顶到预警线以上，内容本身是确定的事实。\n" * 60
setup(long_user, "# 空间记忆\n\n- 短口径。\n")
r = run(["status", "--workspace", WS])
chk("超 80% 时 status 报 ⚠ 且写明 80%",
    r.returncode == 0 and "⚠" in r.stdout and "80%" in r.stdout, r.stdout)

before = [md5(USER_MEM), md5(SPACE_MEM)]
r = run(["check", "--workspace", WS])
chk("check 输出两份文件的字符与行数",
    "用户级" in r.stdout and "空间级" in r.stdout and "/3000 字符" in r.stdout, r.stdout[:200])
chk("check 只读，两份文件 md5 不变", before == [md5(USER_MEM), md5(SPACE_MEM)])

print("[2] 四类候选检出")
setup(
    "# 用户记忆\n\n"
    "- 有歧义、多解、关键信息缺失、意图不确定 → 先问，不假定开工；永不过期。\n"
    "- 规则里写「不确定」是描述场景，不应被当成推测词误报。\n",
    "# 空间记忆\n\n"
    "- 部署前必须重编译替换二进制并校验线上进程，这条口径重复出现了。\n"
    "- 部署前必须重编译替换二进制并校验线上进程，这条口径重复出现了。\n"
    "- 旧口径：使用旧的发布脚本，已废弃不再生效。\n"
    "- 这个结论大概是成立的，还没找到原始出处。\n",
    "# 日志\n\n- 部署前必须重编译替换二进制并校验线上进程，这条口径重复出现了。\n")
r = run(["check", "--workspace", WS])
out = r.stdout
chk("重复条目被检出", "重复条目" in out, out[-500:])
chk("失效标记被检出", "失效标记" in out, out[-500:])
chk("别处已有被检出", "别处已有" in out, out[-500:])
chk("待核实（推测词）被检出", "待核实" in out, out[-500:])
chk("规则句里的「不确定」不误报", "意图不确定 → 先问" not in out, out[-500:])
chk("候选编号从 #1 起且连续", bool(re.search(r"#1\s", out)) and "#2" in out, out[-500:])

print("[3] apply 的确认闸门")
r = run(["apply", "--workspace", WS])
chk("没给 --ids 被拒（exit 2）", r.returncode == 2 and "必须逐条" in r.stdout, r.stdout)
r = run(["apply", "--ids", "1", "--scope", "user", "--confirm", "--workspace", WS])
chk("用户级一律拒绝（exit 2）", r.returncode == 2 and "全空间共用" in r.stdout, r.stdout)
r = run(["apply", "--ids", "999", "--confirm", "--workspace", WS])
chk("不存在的编号被拒（exit 2）", r.returncode == 2 and "不存在" in r.stdout, r.stdout)
r = run(["apply", "--ids", "abc", "--workspace", WS])
chk("坏 --ids 被拒（exit 2）", r.returncode == 2 and "逗号分隔" in r.stdout, r.stdout)

ids = re.findall(r"#(\d+)\s+\[workspace:", out)
chk("能取到 workspace 范围的候选编号", bool(ids), ids)
pick = ids[0] if ids else "1"
before = md5(SPACE_MEM)
r = run(["apply", "--ids", pick, "--workspace", WS])
chk("干跑字样正确", "干跑" in r.stdout and "未写任何文件" in r.stdout, r.stdout)
chk("干跑零改动", md5(SPACE_MEM) == before)
chk("干跑不生成备份", not os.path.isdir(os.path.join(WS, ".workbuddy", "backups")))

print("[4] apply --confirm 的备份、报告与替换")
r = run(["apply", "--ids", pick, "--confirm", "--workspace", WS])
chk("confirm 执行成功", r.returncode == 0 and "执行" in r.stdout, r.stdout)
chk("确认后文件确实变化", md5(SPACE_MEM) != before)
baks = []
bd = os.path.join(WS, ".workbuddy", "backups")
if os.path.isdir(bd):
    baks = [os.path.join(bd, f) for f in os.listdir(bd) if f.startswith("MEMORY.")]
chk("删前生成备份", len(baks) == 1, baks)
if baks:
    chk("备份保存的是改动前内容", md5(baks[0]) == before)
report = os.path.join(WS, ".workbuddy", "archive", "memory-变更报告.md")
chk("生成变更报告", os.path.isfile(report))
if os.path.isfile(report):
    t = io.open(report, encoding="utf-8").read()
    chk("报告含表头、编号、sha256 与字符前后",
        "记忆整合变更报告" in t and "#" + pick in t and "sha256" in t and "→" in t, t[:300])

setup("# 用户记忆\n\n- 短口径。\n",
      "# 空间记忆\n\n- 旧口径：这条已经不再生效了，需要被替换成新写法。\n"
      "- 另一条长期口径，内容确定且不重复也不在别处出现。\n")
r = run(["check", "--workspace", WS])
rep_ids = re.findall(r"#(\d+)\s+\[workspace:", r.stdout)
if rep_ids:
    r = run(["apply", "--ids", rep_ids[0], "--confirm",
             "--replace", rep_ids[0] + "=新写法：直接走脚本，不再用旧流程。",
             "--workspace", WS])
    chk("--replace 替换生效（旧句消失、新句出现）",
        "旧口径" not in io.open(SPACE_MEM, encoding="utf-8").read()
        and "新写法" in io.open(SPACE_MEM, encoding="utf-8").read(),
        r.stdout)
else:
    chk("--replace 替换生效（旧句消失、新句出现）", False, "没找到候选")

print("[5] 异常与边界")
r = run(["check", "--workspace", os.path.join(BASE, "不存在的工作区")])
chk("空间缺 MEMORY.md 不崩", r.returncode == 0 and "未找到" in r.stdout, r.stdout)
r = run(["status", "--workspace", os.path.join(BASE, "不存在的工作区")])
chk("status 在缺文件时也不崩", r.returncode == 0, r.stdout + r.stderr)
outpath = os.path.join(BASE, "清单.md")
r = run(["check", "--out", outpath, "--workspace", WS])
chk("--out 能写清单文件", os.path.isfile(outpath) and "记忆预算" in io.open(outpath, encoding="utf-8").read())

print("\n结果：%d 通过 / %d 失败" % (PASS, FAIL))
print("临时目录：%s" % BASE)
sys.exit(0 if FAIL == 0 else 1)
