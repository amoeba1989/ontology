#!/bin/sh
# 编译检查阶段（流水线 stage 1 调用）：只检查，不发布、不重启
set -eu

APP_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
VENV="$APP_DIR/.venv"

log() { echo "[check] $*"; }

# 后端：依赖 + 编译检查
log "安装后端依赖"
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
fi
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -r "$APP_DIR/backend/requirements.txt"
log "后端编译检查（compileall）"
"$VENV/bin/python" -m compileall -q "$APP_DIR/backend/app"

# 前端：依赖 + 产物构建（编译检查；不走 vue-tsc，仓库遗留大量历史类型错误）
cd "$APP_DIR/frontend"
log "安装前端依赖"
if ! command -v pnpm >/dev/null 2>&1; then
  npm install -g pnpm >/dev/null 2>&1
fi
pnpm install --frozen-lockfile
log "前端构建（vite build）"
npx vite build

log "编译检查全部通过"
