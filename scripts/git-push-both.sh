#!/bin/sh
# 双远程推送：gitee 与 github 使用同一个 master 分支。
# 单位里访问不到 GitHub 时照常运行本脚本，GitHub 那一侧会失败并跳过，
# 不影响 Gitee 推送与 Gitee Go 触发；回到能访问 GitHub 的网络再补推即可。
#
# 用法：sh scripts/git-push-both.sh [分支名]   # 默认 master
set -u
BRANCH="${1:-master}"

pushed=""
failed=""
for remote in gitee github; do
  url=$(git remote get-url "$remote" 2>/dev/null) || {
    echo "[push] 尚未配置 remote ${remote}，跳过"
    failed="$failed $remote(未配置)"
    continue
  }
  echo "[push] ${remote} -> ${url}"
  # GIT_TERMINAL_PROMPT=0：凭证缺失时立刻失败，而不是卡在交互式输入上
  if GIT_TERMINAL_PROMPT=0 timeout 300 git push "$remote" "$BRANCH"; then
    pushed="$pushed $remote"
  else
    echo "[push] ${remote} 推送失败（网络不可达或凭证问题），不影响其他远程"
    failed="$failed $remote"
  fi
done

echo "[push] 成功:${pushed:- 无} | 未成功:${failed:- 无}"
[ -z "$failed" ] || exit 1
