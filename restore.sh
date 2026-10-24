#!/usr/bin/env bash
# 技能恢复脚本（macOS / Linux / Windows 的 Git Bash）
# 用法：bash restore.sh            正式恢复
#      DRY_RUN=1 bash restore.sh   只演练
#      TARGET=/custom/path bash restore.sh
set -euo pipefail

TARGET="${TARGET:-$HOME/.workbuddy/skills}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/skills"
DRY="${DRY_RUN:-0}"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="${TMPDIR:-/tmp}/wb_skills_replaced_${STAMP}"

echo "=== WorkBuddy 技能恢复 ==="
echo "来源: $SRC"
echo "目标: $TARGET"
[ "$DRY" = "1" ] && echo "模式: 演练（不写文件）"
echo

[ -d "$SRC" ] || { echo "找不到 skills 目录"; exit 1; }
[ "$DRY" = "1" ] || mkdir -p "$TARGET"

n=0
for d in "$SRC"/*/; do
  name="$(basename "$d")"
  dest="$TARGET/$name"
  if [ -e "$dest" ]; then
    if [ "$DRY" = "1" ]; then
      echo "  [演练] 已存在，将备份后覆盖: $name"
    else
      mkdir -p "$BACKUP"
      mv "$dest" "$BACKUP/$name"
      echo "  已备份旧版: $name -> $BACKUP"
    fi
  fi
  if [ "$DRY" != "1" ]; then
    cp -R "$d" "$dest"
    echo "  已安装: $name"
  fi
  n=$((n+1))
done

echo
echo "完成: $n 个技能"
echo "已装技能数校验: $(find "$TARGET" -maxdepth 2 -name SKILL.md 2>/dev/null | wc -l) 个 SKILL.md"

if [ -f "$TARGET/html-shot/package.json" ] && command -v npm >/dev/null 2>&1 && [ "$DRY" != "1" ]; then
  echo "安装 html-shot 依赖..."
  ( cd "$TARGET/html-shot" && npm install --omit=dev --no-audit --no-fund >/dev/null 2>&1 && echo "  完成" ) || echo "  npm install 失败，需手动处理"
fi

echo
echo "下一步：完全退出并重开 WorkBuddy，技能列表才刷新。"
[ -d "$BACKUP" ] && echo "旧版备份: $BACKUP"
