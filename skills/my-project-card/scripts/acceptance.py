# -*- coding: utf-8 -*-
"""my-project-card 回归验收：改完引擎跑一遍，29 项检查。

用法： python scripts/acceptance.py
退出码 0 表示全过。改数据结构或写入逻辑后必跑。
"""
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

CARD = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "card.py")
S = os.path.join(tempfile.gettempdir(), "card-acceptance")
ok = fail = 0


def run(*args, cwd=None):
    return subprocess.run([sys.executable, CARD] + list(args),
                          capture_output=True, text=True, encoding="utf-8", cwd=cwd)


def chk(name, cond, detail=""):
    global ok, fail
    if cond:
        ok += 1
        print("  PASS  %s" % name)
    else:
        fail += 1
        print("  FAIL  %s  %s" % (name, detail))


if os.path.isdir(S):
    shutil.rmtree(S)

print("[1] 建卡与基础写入")
r = run("init", "--project", "验收项目", "--slug", "acc", "--books", "web", "assets", "--store", S)
chk("init 成功", r.returncode == 0, r.stdout + r.stderr)
for sec, txt in [("目标", "交付一个可玩的三合一扑克小游戏"),
                 ("口径", "线上发布走 appId wx123"),
                 ("排除", "不做实时对战，因为服务器成本过高")]:
    r = run("add", "--slug", "acc", "--section", sec, "--text", txt, "--store", S)
    chk("add 主卡 %s" % sec, r.returncode == 0, r.stdout + r.stderr)
r = run("add", "--slug", "acc", "--book", "web", "--section", "待办",
        "--text", "发牌动画改到 0.3 秒", "--store", S)
chk("add 分册待办", r.returncode == 0, r.stdout + r.stderr)
r = run("add", "--slug", "acc", "--book", "web", "--section", "坑",
        "--text", "ffmpeg 转 WebP 会丢透明通道，要加 -pix_fmt", "--store", S)
chk("add 分册坑", r.returncode == 0, r.stdout + r.stderr)
_web = open(os.path.join(S, "acc", "books", "web.md"), encoding="utf-8").read()
_sec = _web.split("## 4. 待办")[1].split("## 5.")[0]
chk("写入后占位符已清除", "_（暂无记录）_" not in _sec, _sec)

print("[2] 查重与拒绝")
r = run("add", "--slug", "acc", "--book", "web", "--section", "待办",
        "--text", "发牌动画改到 0.3 秒", "--store", S)
chk("重复条目不写入", r.returncode == 2, "退出码 %d" % r.returncode)
r = run("add", "--slug", "acc", "--book", "web", "--section", "待办",
        "--text", "改发牌音效", "--store", S)
chk("短句不同内容不误判", r.returncode == 0, r.stdout)
r = run("add", "--slug", "acc", "--section", "口径", "--text", "端口应该是 8080", "--store", S)
chk("推测词被拒", r.returncode == 1, r.stdout)
r = run("add", "--slug", "acc", "--section", "口径", "--text", "数据库密码: Abcd1234", "--store", S)
chk("明文凭据被拒", r.returncode == 1, r.stdout)

print("[3] 会话登记与并发可见")
os.makedirs(os.path.join(S, "ws-a"), exist_ok=True)
os.makedirs(os.path.join(S, "ws-b"), exist_ok=True)
r = run("claim", "--slug", "acc", "--book", "web", "--note", "在改发牌动画",
        "--session", "aaaa", "--store", S, cwd=os.path.join(S, "ws-a"))
chk("claim 成功", r.returncode == 0, r.stdout)
r = run("claim", "--slug", "acc", "--book", "web", "--note", "在改音效",
        "--session", "bbbb", "--store", S, cwd=os.path.join(S, "ws-b"))
chk("同工作面冲突提示", "同一工作面" in r.stdout, r.stdout)
r = run("resume", "--slug", "acc", "--store", S)
chk("resume 显示在做什么", "正在做什么" in r.stdout and "在改发牌动画" in r.stdout, r.stdout)
chk("resume 显示最近发生", "最近发生" in r.stdout, r.stdout)
lines = len(r.stdout.splitlines())
chk("resume 输出不超过 45 行（实际 %d）" % lines, lines <= 45)

print("[4] 改写与失效")
mainf = os.path.join(S, "acc", "context-card.md")
txt = open(mainf, encoding="utf-8").read()
oid = [ln.split("#")[1].split()[0] for ln in txt.splitlines() if "线上发布走 appId" in ln][0]
r = run("revise", "--slug", "acc", "--id", oid, "--text", "线上发布改走 appId wx999", "--store", S)
chk("revise 成功", r.returncode == 0, r.stdout + r.stderr)
txt2 = open(mainf, encoding="utf-8").read()
chk("旧条目变已失效", "已失效" in txt2 and oid in txt2)
chk("新条目在", "wx999" in txt2)
chk("旧内容仍可查", "wx123" in txt2)

print("[5] 检索与体检")
r = run("search", "--slug", "acc", "--keyword", "透明通道", "--store", S)
chk("search 命中分册", "透明通道" in r.stdout and "命中" in r.stdout, r.stdout)
r = run("check", "--slug", "acc", "--store", S)
chk("check 通过", r.returncode == 0, r.stdout)
r = run("list", "--store", S)
chk("list 列出卡", "acc" in r.stdout, r.stdout)

print("[6] 八进程并发写同一分册")
PARA = ["素材目录统一转成 WebP 格式", "音效播放器加上随机偏移", "发牌逻辑抽成独立模块",
        "移动端适配横屏分辨率", "背包数据改成 JSON 存储", "联机房间增加超时踢人",
        "动画帧率限制到六十帧", "日志输出加上会话编号"]
bakdir = os.path.join(S, "acc", "backups")
before = len(os.listdir(bakdir))


def add_one(i):
    return run("add", "--slug", "acc", "--book", "assets", "--section", "待办",
               "--text", PARA[i], "--store", S)


with ThreadPoolExecutor(max_workers=8) as ex:
    rs = list(ex.map(add_one, range(8)))
codes = [x.returncode for x in rs]
chk("八个进程全部成功 %s" % codes, all(c == 0 for c in codes),
    " | ".join((x.stdout + x.stderr)[:40] for x in rs if x.returncode))
body = open(os.path.join(S, "acc", "books", "assets.md"), encoding="utf-8").read()
kept = [ln for ln in body.splitlines() if ln.startswith("- ")]
chk("八条全部保留（实际 %d）" % len(kept), len(kept) == 8, body)
baks = os.listdir(bakdir)
chk("备份新增 8 份（实际 %d）" % (len(baks) - before), len(baks) - before == 8)
chk("备份无重复文件名", len(baks) == len(set(baks)))

print("[7] 备份收敛")
r = run("gc", "--slug", "acc", "--keep", "3", "--store", S)
after = len(os.listdir(bakdir))
chk("gc 收敛备份到 3 份（实际 %d）" % after, after == 3, r.stdout)

print("[8] 工作区简报")
r = run("mirror", "--slug", "acc", "--workspace", os.path.join(S, "ws-a"), "--store", S)
mf = os.path.join(S, "ws-a", ".workbuddy", "PROJECT_CONTEXT.md")
chk("简报生成", os.path.isfile(mf), r.stdout)
chk("简报含只读提示", "只读" in open(mf, encoding="utf-8").read())

print("\n结果：%d 通过 / %d 失败" % (ok, fail))
sys.exit(0 if fail == 0 else 1)
