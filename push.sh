#!/usr/bin/env bash
# 把技能快照推到 GitHub。用法：
#   GH_TOKEN=github_pat_xxx bash push.sh
# token 不会被写入任何文件，也不会留在 git remote 里。
set -euo pipefail

if [ -z "${GH_TOKEN:-}" ]; then
  echo "缺少 GH_TOKEN。用法：GH_TOKEN=你的token bash push.sh" >&2
  exit 1
fi

REPO="${REPO:-Joshuataokun/workbuddy-skills}"
BRANCH="${BRANCH:-main}"
cd "$(dirname "${BASH_SOURCE[0]}")"

echo "目标仓库: https://github.com/$REPO"
echo "当前提交: $(git rev-parse --short HEAD)  ($(git ls-files | wc -l) 个文件)"

git remote remove origin 2>/dev/null || true
git remote add origin "https://github.com/$REPO.git"

AUTH="$(printf 'x-access-token:%s' "$GH_TOKEN" | base64 | tr -d '\n')"
git -c credential.helper= -c http.extraheader="AUTHORIZATION: basic $AUTH" push -u origin "$BRANCH"

git remote set-url origin "https://github.com/$REPO.git"
echo
echo "推送完成。检查： https://github.com/$REPO"
echo "建议：推送成功后立刻到 GitHub 设置里 Revoke 这个 token。"
