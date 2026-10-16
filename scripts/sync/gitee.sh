#!/usr/bin/env bash
# Both remotes must already be authenticated. Only fast-forward updates are allowed.
set -euo pipefail

github_branch=${GITHUB_SYNC_BRANCH:-main}
gitee_branch=${GITEE_SYNC_BRANCH:-}
git check-ref-format "refs/heads/$github_branch"
if [[ -z "$gitee_branch" ]]; then
  gitee_branch=$(git ls-remote --symref gitee HEAD | awk '$1 == "ref:" && $3 == "HEAD" {sub(/^refs\/heads\//, "", $2); print $2}')
fi
if [[ -z "$gitee_branch" ]]; then
  echo '::error::Cannot detect Gitee default branch. Set repository variable GITEE_SYNC_BRANCH.'
  exit 1
fi
git check-ref-format "refs/heads/$gitee_branch"
git fetch --no-tags origin "refs/heads/$github_branch:refs/remotes/origin/$github_branch"
git fetch --no-tags gitee "refs/heads/$gitee_branch:refs/remotes/gitee/$gitee_branch"
gh_ref="refs/remotes/origin/$github_branch"
ge_ref="refs/remotes/gitee/$gitee_branch"
gh_sha=$(git rev-parse "$gh_ref")
ge_sha=$(git rev-parse "$ge_ref")
if [[ "$gh_sha" == "$ge_sha" ]]; then
  echo "Already synchronized: $gh_sha"
elif git merge-base --is-ancestor "$gh_ref" "$ge_ref"; then
  git push origin "$ge_ref:refs/heads/$github_branch"
  echo "Gitee -> GitHub: $ge_sha"
elif git merge-base --is-ancestor "$ge_ref" "$gh_ref"; then
  git push gitee "$gh_ref:refs/heads/$gitee_branch"
  echo "GitHub -> Gitee: $gh_sha"
else
  echo '::error::Branches have diverged. Merge their histories and resolve conflicts before retrying. Neither remote was changed.'
  exit 1
fi
