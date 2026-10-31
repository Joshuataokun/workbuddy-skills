#!/usr/bin/env bash
# 把本机技能同步回仓库并推送。
# 用法： bash sync.sh "本次改了什么"
#        DRY_RUN=1 bash sync.sh      只看会同步哪些文件，不提交不推送
#        PRUNE=0 bash sync.sh        不清理仓库里本机已没有的技能目录
#        SRC=/自定义/技能目录 bash sync.sh
#
# 默认镜像同步：仓库 skills/ 是本机的精确镜像，本机删了就跟着删。
# 想留孤儿目录时用 PRUNE=0，或把目录挪到 skills/ 之外（如 _retired/，已 gitignore）。
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"
SRC="${SRC:-$HOME/.workbuddy/skills}"
MSG="${1:-chore: 同步本机技能 $(date +%Y-%m-%d\ %H:%M)}"
DRY="${DRY_RUN:-0}"
PRUNE="${PRUNE:-1}"

echo "=== 同步本机技能 → 仓库 ==="
echo "来源: $SRC"
echo "仓库: $(pwd)"
[ "$DRY" = "1" ] && echo "模式: 演练（不提交、不推送）"
echo

[ -d "$SRC" ] || { echo "找不到技能目录: $SRC"; exit 1; }

n=0
for d in "$SRC"/*/; do
  name="$(basename "$d")"
  [ -f "$d/SKILL.md" ] || continue          # 只同步真正的技能
  case "$name" in *.bak*|*_old*|*_backup*) echo "  跳过备份目录: $name"; continue;; esac
  dest="skills/$name"
  rm -rf "$dest"
  mkdir -p "$dest"
  # 排除可重建 / 无用的内容；reports 含本机绝对路径，不得进公开仓库
  ( cd "$d" && tar -cf - \
      --exclude='node_modules' --exclude='.git' --exclude='__pycache__' \
      --exclude='*.zip' --exclude='*.pyc' --exclude='reports' \
      --exclude='*.bak-*' --exclude='*.tmp' . ) | ( cd "$dest" && tar -xf - )
  echo "  已同步: $name"
  n=$((n+1))
done

# 镜像清理：仓库里有、本机已经没有的技能目录
if [ "$n" -eq 0 ]; then
  echo "❌ 本机一个技能都没扫到，疑似 SRC 指错了。已中止，避免把仓库清空。"
  exit 1
fi
if [ "$PRUNE" = "1" ]; then
  echo
  echo "--- 清理仓库侧孤儿（仓库有、本机无）---"
  p=0
  for d in skills/*/; do
    [ -d "$d" ] || continue
    name="$(basename "$d")"
    if [ -f "$SRC/$name/SKILL.md" ]; then
      continue
    fi
    rm -rf "skills/$name"
    echo "  已清理: $name"
    p=$((p+1))
  done
  if [ "$p" -eq 0 ]; then
    echo "  无，仓库与本机一致"
  fi
else
  echo
  echo "跳过孤儿清理（PRUNE=0）"
fi

# 重新生成 manifest.json（有 python 才做）
PY=""
for c in python3 python; do command -v "$c" >/dev/null 2>&1 && { PY="$c"; break; }; done
if [ -n "$PY" ]; then
  "$PY" - <<'PYEOF'
import hashlib, json, pathlib, re

WIN = re.compile(r"[A-Za-z]:\\Users\\[^\\]+\\.workbuddy\\skills\\")
POSIX = re.compile(r"/(?:Users|home)/[^/]+/\.workbuddy/skills/")

def scrub(s):
    s = WIN.sub(r"<SKILLS_ROOT>\\", s)
    s = POSIX.sub("<SKILLS_ROOT>/", s)
    return s

def walk(o):
    if isinstance(o, dict):
        return {k: walk(v) for k, v in o.items()}
    if isinstance(o, list):
        return [walk(v) for v in o]
    if isinstance(o, str):
        return scrub(o)
    return o

scrubbed = 0
for p in pathlib.Path("skills").rglob("*.json"):
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        continue
    new = walk(data)
    if new != data:
        p.write_text(json.dumps(new, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        scrubbed += 1

root = pathlib.Path("skills")
entries = []
for d in sorted(p for p in root.iterdir() if p.is_dir()):
    files = [f for f in d.rglob("*") if f.is_file()]
    skill = d / "SKILL.md"
    h = hashlib.sha256(skill.read_bytes()).hexdigest()[:16] if skill.exists() else ""
    meta = d / "_skillhub_meta.json"
    src = "local"
    if meta.exists():
        try:
            src = json.loads(meta.read_text(encoding="utf-8")).get("source", "marketplace")
        except Exception:
            src = "marketplace"
    entries.append({"dir": d.name, "source": src, "files": len(files),
                    "bytes": sum(f.stat().st_size for f in files),
                    "sha256_of_manifest": h})
json.dump({"synced_at": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
           "skills_count": len(entries),
           "total_bytes": sum(e["bytes"] for e in entries),
           "skills": entries},
          open("manifest.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"manifest.json 已更新：{len(entries)} 个技能；脱敏文件：{scrubbed} 个")
PYEOF
else
  echo "⚠️ 本机没有 python，跳过 manifest.json 更新（不影响技能本身）"
fi

echo
echo "已同步 $n 个技能"
git add -A
if git diff --cached --quiet; then
  echo "没有变化，无需提交。"
  exit 0
fi
echo "--- 变更摘要 ---"
git diff --cached --stat | tail -15

if [ "$DRY" = "1" ]; then
  echo
  echo "演练结束：以上变更**未提交**。去掉 DRY_RUN=1 再跑一次即可提交并推送。"
  exit 0
fi

git commit -q -m "$MSG"
echo
echo "已提交: $(git log --oneline -1)"
echo "开始推送（首次会弹出 GitHub 授权页，点同意即可，之后不再询问）..."
git push -u origin main
echo
echo "完成。仓库: https://github.com/$(git remote get-url origin | sed 's|.*github.com[:/]||; s|\.git$||')"
