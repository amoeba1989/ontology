#!/bin/sh
# 知彼本体平台 ECS 部署脚本（由流水线 deploy@agent 在仓库根目录内调用）
# 前置：ECS 上已 git clone 本仓库到 /opt/ontology（见流水线 script），装有 python3/venv、git
# 可选：nginx（前端静态托管），systemd（后端守护，见 scripts/deploy/ontology-backend.service）
set -eu

APP_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
VENV="$APP_DIR/.venv"
DIST_ROOT="${DIST_ROOT:-/var/www/ontology}"
BACKEND_PORT="${BACKEND_PORT:-8001}"
RUN_DIR="$APP_DIR/run"
PID_FILE="$RUN_DIR/uvicorn.pid"
LOG_FILE="$RUN_DIR/uvicorn.log"

log() { echo "[deploy] $*"; }

# 1) 后端：依赖 + 编译检查（失败即中止，不影响在跑的旧版本）
log "安装后端依赖"
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
fi
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -r "$APP_DIR/backend/requirements.txt"
log "后端编译检查（compileall）"
"$VENV/bin/python" -m compileall -q "$APP_DIR/backend/app"

# 2) 前端：依赖 + 产物构建（编译检查；不走 vue-tsc，仓库遗留大量历史类型错误）
cd "$APP_DIR/frontend"
log "安装前端依赖"
if ! command -v pnpm >/dev/null 2>&1; then
  npm install -g pnpm >/dev/null 2>&1
fi
pnpm install --frozen-lockfile
log "前端构建（vite build）"
npx vite build

# 3) 发布前端静态资源
log "发布静态资源 -> $DIST_ROOT"
mkdir -p "$DIST_ROOT"
if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete dist/ "$DIST_ROOT/"
else
  rm -rf "$DIST_ROOT"/*
  cp -r dist/. "$DIST_ROOT/"
fi

# 4) 重启后端
mkdir -p "$RUN_DIR"
cd "$APP_DIR/backend"
if systemctl list-unit-files 2>/dev/null | grep -q "^ontology-backend.service"; then
  log "systemd 重启 ontology-backend"
  systemctl restart ontology-backend
else
  if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    log "停止旧后端进程 $(cat "$PID_FILE")"
    kill "$(cat "$PID_FILE")" || true
    sleep 2
  fi
  log "nohup 启动 uvicorn :$BACKEND_PORT（日志 $LOG_FILE）"
  nohup "$VENV/bin/uvicorn" app.main:app --host 127.0.0.1 --port "$BACKEND_PORT" \
    >>"$LOG_FILE" 2>&1 &
  echo $! >"$PID_FILE"
fi

# 5) 健康检查
log "等待后端就绪"
i=0
until curl -sf "http://127.0.0.1:$BACKEND_PORT/api/v1/scene-registry" >/dev/null; do
  i=$((i + 1))
  if [ "$i" -gt 30 ]; then
    log "后端健康检查超时，查看 $LOG_FILE"
    exit 1
  fi
  sleep 2
done
log "后端就绪"

# 6) 演示数据（幂等；首次部署时补齐场景演示库）
log "灌演示种子数据（幂等）"
"$VENV/bin/python" scripts/seed_mil_demo.py
"$VENV/bin/python" scripts/seed_drone_demo.py

# 7) nginx：若已安装则安装配置并重载
if command -v nginx >/dev/null 2>&1; then
  if [ -w /etc/nginx/conf.d ] || [ "$(id -u)" = "0" ]; then
    cp "$APP_DIR/scripts/deploy/nginx-ontology.conf" /etc/nginx/conf.d/ontology.conf
    if nginx -t 2>/dev/null; then
      systemctl reload nginx 2>/dev/null || nginx -s reload
      log "nginx 配置已更新"
    else
      log "警告：nginx 配置校验未过，请手动检查 /etc/nginx/conf.d/ontology.conf"
    fi
  fi
else
  log "未检测到 nginx：前端 dist 在 $DIST_ROOT，请自行配置静态托管（参考 scripts/deploy/nginx-ontology.conf）"
fi

log "部署完成：后端 127.0.0.1:$BACKEND_PORT，前端静态目录 $DIST_ROOT"
