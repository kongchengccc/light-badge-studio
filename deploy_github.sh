#!/usr/bin/env bash
# 一键创建 GitHub 仓库并推送（需要 gh 已登录：gh auth login）
set -euo pipefail
REPO="${1:-light-badge-studio}"
VIS="${2:-public}"
cd "$(dirname "$0")"

if ! gh auth status >/dev/null 2>&1; then
  echo "请先登录： gh auth login" >&2
  exit 1
fi

if gh repo view "$(gh api user -q .login)/$REPO" >/dev/null 2>&1; then
  echo "仓库已存在，直接推"
else
  gh repo create "$REPO" --"$VIS" --source=. --remote=origin --description "上传灯牌视频，自动逆向动态效果，文字/头像/字体可编辑并导出带 Alpha 的 MOV" || true
  git remote add origin "git@github.com:$(gh api user -q .login)/$REPO.git" 2>/dev/null || true
fi

git remote -v | head -2
git push -u origin main
echo
echo "✅ 已推送： https://github.com/$(gh api user -q .login)/$REPO"
